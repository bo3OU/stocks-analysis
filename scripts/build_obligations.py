"""Obligations, dilution and financing-terms tables from XBRL facts and offering-document text.

Outputs (RESEARCH_DIR/tables/): obligations_xbrl.csv (latest period facts for debt, maturities, leases, purchase commitments,
dilutive securities, share counts, equity/debt raises, shelf fee-table facts), obligations_xbrl.md (short view), offerings.csv
(offering terms found by pattern in 424B*, S-1/S-3, F-1/F-3, 6-K and financing 8-Ks, with line numbers). Facts come from the folder's
companyfacts.json (already cut at the cutoff in as-of folders); offering rows are PATTERN HITS to confirm in the cited lines.
Usage: .venv/bin/python -I scripts/build_obligations.py <TICKER or RESEARCH_DIR> [--periods 6]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if not (Path(__file__).resolve().parent / "toolkit.py").is_file():
    sys.path.insert(1, str(Path(__file__).resolve().parents[3] / "scripts"))
from build_digest import parse_header  # noqa: E402
from toolkit import _numbered_lines, clean_cell, fail, parse_date, read_csv, research_dir, write_atomic, write_csv  # noqa: E402

FAMILIES = [
    ("share_counts", r"^(EntityCommonStockSharesOutstanding|CommonStockSharesOutstanding|CommonStockSharesIssued)$"),
    ("debt", r"^(LongTermDebt|LongTermDebtCurrent|LongTermDebtNoncurrent|ConvertibleNotesPayable\w*|ConvertibleLongTermNotesPayable|NotesPayable\w*|LineOfCredit\w*|DebtCurrent|ShortTermBorrowings|DebtInstrument(FaceAmount|CarryingAmount|FairValue|InterestRateStatedPercentage|ConvertibleConversionPrice\d?|ConvertibleConversionRatio\d?|MaturityDate))$"),
    ("debt_maturities", r"^LongTermDebtMaturitiesRepaymentsOfPrincipal\w*$"),
    ("leases", r"^(OperatingLeaseLiability\w*|FinanceLeaseLiability\w*|LesseeOperatingLeaseLiabilityPaymentsDue\w*|LesseeFinanceLeaseLiabilityPaymentsDue\w*|CapitalLeaseObligations\w*)$"),
    ("purchase_commitments", r"^(PurchaseObligation\w*|UnrecordedUnconditionalPurchaseObligation\w*|ContractualObligation\w*)$"),
    ("dilutive_securities", r"^(AntidilutiveSecuritiesExcludedFromComputationOfEarningsPerShareAmount|ClassOfWarrantOrRight\w*|ShareBasedCompensationArrangementByShareBasedPaymentAward(OptionsOutstandingNumber|OptionsExercisableNumber|EquityInstrumentsOtherThanOptionsNonvestedNumber|NumberOfSharesAvailableForGrant)|EmployeeServiceShareBasedCompensationNonvestedAwardsTotalCompensationCostNotYetRecognized)$"),
    ("raises", r"^(StockIssuedDuringPeriodValueNewIssues|StockIssuedDuringPeriodSharesNewIssues|ProceedsFromIssuanceOfCommonStock|ProceedsFromIssuanceOrSaleOfEquity|ProceedsFromIssuanceOfDebt|ProceedsFromConvertibleNotesPayable|ProceedsFromNotesPayable)$"),
]
FAM_RES = [(n, re.compile(p)) for n, p in FAMILIES]
PERIODIC = ("10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F", "10-KT")
OFFERING_FORMS = ("424B5", "424B3", "424B2", "424B4", "424B7", "S-1", "S-1/A", "S-3", "S-3ASR", "F-3", "F-1")
FIN_8K_ITEMS = ("1.01", "2.03", "3.02")
# Prospectus summaries can precede the actual note and conversion terms by
# thousands of converted-text lines (including in the VKTX 424B5 sample).
SCAN_LINES = 20000
UNIT = r"(?:\s*(million|billion))?"
PATTERNS = [
    ("shares_offered", re.compile(r"([\d,]{5,})\s+shares of (?:our |the Company's )?(?:common stock|ordinary shares|Class [AB] common stock)", re.I)),
    ("price_per_share", re.compile(r"\$\s?(\d{1,4}(?:\.\d{1,4})?)\s+per (?:share|ordinary share)", re.I)),
    ("aggregate_amount", re.compile(r"(?:aggregate (?:offering price|principal amount|gross proceeds)|gross proceeds)[^$\n]{0,80}\$\s?([\d,]+(?:\.\d+)?)" + UNIT, re.I)),
    ("notes_terms", re.compile(r"\$\s?([\d,]+(?:\.\d+)?)" + UNIT + r"\s+(?:aggregate principal amount of\s+)?(\d+(?:\.\d+)?)%\s+(?:convertible\s+)?(?:senior\s+)?(?:notes|debentures)\s+due\s+(\d{4})", re.I)),
    ("conversion_price", re.compile(r"(?:initial )?conversion price of (?:approximately )?\$\s?([\d,]+(?:\.\d+)?)", re.I)),
    ("conversion_rate", re.compile(r"conversion rate of (?:approximately )?([\d,]+(?:\.\d+)?) shares", re.I)),
    ("net_proceeds", re.compile(r"net proceeds[^$\n]{0,100}\$\s?([\d,]+(?:\.\d+)?)" + UNIT, re.I)),
    ("greenshoe_option", re.compile(r"(?:option|right) to purchase (?:up to )?(?:an )?(?:additional )?([\d,]+) (?:additional )?shares|additional \$\s?([\d,]+(?:\.\d+)?)" + UNIT + r" (?:aggregate principal amount|of notes)", re.I)),
]


def xbrl_rows(rd: Path, periods: int) -> list[dict]:
    p = rd / "raw" / "sec" / "companyfacts.json"
    if any(q.is_symlink() for q in (rd / "raw", rd / "raw" / "sec", p)):
        print(f"WARNING: skipping symlinked XBRL input: {p}", file=sys.stderr)
        return []
    if not p.is_file():
        print(f"WARNING: XBRL input unavailable: {p}", file=sys.stderr)
        return []
    facts = json.loads(p.read_text(encoding="utf-8", errors="replace")).get("facts", {})
    out = []
    for tax, tags in facts.items():
        for concept, body in tags.items():
            fam = "shelf_fee_table" if tax == "ffd" else next((n for n, rx in FAM_RES if rx.match(concept)), None)
            if not fam:
                continue
            for unit, fl in (body.get("units") or {}).items():
                best = {}
                for f in fl:
                    if tax != "ffd" and f.get("form") not in PERIODIC:
                        continue
                    end = parse_date(f.get("end"))
                    if not end:
                        continue
                    key = (f.get("start") or "", f.get("end"))
                    if key not in best or (f.get("filed") or "") > (best[key].get("filed") or ""):
                        best[key] = f
                latest = sorted(best.items(), key=lambda kv: (kv[0][1], kv[0][0]), reverse=True)[:periods]
                for (start, end), f in latest:
                    out.append({"family": fam, "taxonomy": tax, "concept": concept, "unit": unit, "start": start, "end": end, "value": f.get("val"),
                                "form": f.get("form", ""), "filed": f.get("filed", ""), "accession": f.get("accn", "")})
    out.sort(key=lambda r: (r["family"], r["concept"], r["unit"], r["end"], r["start"]), reverse=False)
    if out:
        newest = max(r["end"] for r in out if r["taxonomy"] != "ffd") if any(r["taxonomy"] != "ffd" for r in out) else None
        # Feb 29 has no counterpart two years earlier; use the last day of February.
        newest_date = parse_date(newest)
        if newest_date:
            try:
                cut = newest_date.replace(year=newest_date.year - 2).isoformat()
            except ValueError:
                cut = newest_date.replace(year=newest_date.year - 2, day=28).isoformat()
        else:
            cut = ""
        latest_by = {}
        for r in out:
            k = (r["taxonomy"], r["concept"], r["unit"])
            latest_by[k] = max(latest_by.get(k, ""), r["end"])
        for r in out:
            r["stale"] = "yes" if r["taxonomy"] != "ffd" and cut and latest_by[(r["taxonomy"], r["concept"], r["unit"])] < cut else ""
    return out


def offering_rows(rd: Path) -> list[dict]:
    idx_path = rd / "filings_index.csv"
    if idx_path.is_symlink():
        print(f"WARNING: skipping symlinked filings index: {idx_path}", file=sys.stderr)
        idx = {}
    else:
        idx = {r.get("accessionNumber", ""): r for r in read_csv(idx_path)}
    tdir = rd / "text"
    if not tdir.is_dir() or tdir.is_symlink():
        return []
    rows = []
    for p in sorted(tdir.glob("*.txt")):
        if p.is_symlink() or not p.is_file():
            continue
        lines = _numbered_lines(p.read_text(encoding="utf-8", errors="replace"))
        meta = parse_header(lines)
        form = meta["form"]
        indexed_items = idx.get(meta["accession"], {}).get("items") or ""
        header_items = " ".join(ln.split("ITEMS:", 1)[1] for ln in lines[:6] if "ITEMS:" in ln)
        items = set(re.findall(r"\b[1-9]\.\d{2}\b", indexed_items + " " + header_items))
        is_offering = (form in OFFERING_FORMS or form.startswith("424B") or
                       form.startswith(("S-1/", "S-3/", "S-3ASR/", "F-1/", "F-3/", "F-3ASR", "6-K")))
        if not is_offering and not (form.startswith("8-K") and any(i in items for i in FIN_8K_ITEMS)):
            continue
        per: dict[str, int] = {}
        if len(lines) > SCAN_LINES:
            print(f"WARNING: {p.name}: offering scan limited to first {SCAN_LINES} lines", file=sys.stderr)
        for i, raw in enumerate(lines[:SCAN_LINES], 1):
            for field, rx in PATTERNS:
                for m in rx.finditer(raw):
                    ctx = raw[max(0, m.start() - 120): m.end() + 120]
                    if field == "shares_offered" and (not re.search(r"offer|sell|sale|purchas", ctx, re.I) or re.search(r"outstanding|authorized|exercise|unvested|restricted|reserved", ctx, re.I)):
                        continue
                    # Indenture formulas often say "per $1,000 aggregate principal amount"
                    # and mention another dollar figure later on the same line. That later
                    # figure is not the size of the offering.
                    if field == "aggregate_amount" and re.search(
                        r"\bper\s+\$\s?[\d,]+(?:\.\d+)?\s*$", raw[max(0, m.start() - 45):m.start()], re.I
                    ):
                        continue
                    shown = field
                    if field == "price_per_share":
                        pricing_cue = re.search(r"offering price|price to the public|public offering|purchase price|issue price|at a price", ctx, re.I)
                        # Use the label before this amount: a table row may contain
                        # both the public price and an underwriting discount.
                        before_price = raw[max(0, m.start() - 80):m.start()]
                        fee_cue = re.search(r"underwriting (?:discount|commission)|\bconcession\b|selling commission", before_price, re.I)
                        shown = "offering_price" if pricing_cue and not fee_cue else "price_mention"
                    if per.get(shown, 0) >= 6:
                        continue
                    per[shown] = per.get(shown, 0) + 1
                    vals = [g for g in m.groups() if g]
                    rows.append({"file": p.name, "form": form, "filed": meta["filed"], "accession": meta["accession"], "field": shown, "value": " ".join(vals), "line": i,
                                 "snippet": clean_cell(raw[max(0, m.start() - 40): m.end() + 40], 200)})
                    if per[shown] >= 6:
                        break
    return sorted(rows, key=lambda r: (r["filed"], r["file"], r["line"], r["field"]), reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--periods", type=int, default=6)
    a = ap.parse_args()
    if a.periods < 1:
        ap.error("--periods must be positive")
    rd = research_dir(a.folder)
    x = xbrl_rows(rd, a.periods)
    o = offering_rows(rd)
    out = rd / "tables"
    if out.is_symlink():
        fail(f"refusing to write through a symlink: {out}")
    write_csv(out / "obligations_xbrl.csv", ["family", "taxonomy", "concept", "unit", "start", "end", "value", "form", "filed", "accession", "stale"], x)
    write_csv(out / "offerings.csv", ["file", "form", "filed", "accession", "field", "value", "line", "snippet"], o)
    md = [f"# Obligations and financing terms: {rd.name}", "Built by scripts/build_obligations.py. XBRL facts are as filed (latest periods per concept); offering rows are pattern hits: confirm in the cited lines (`read_section.py`).", ""]
    if any(q.is_symlink() for q in (rd / "raw", rd / "raw" / "sec", rd / "raw" / "sec" / "companyfacts.json")) or not (rd / "raw" / "sec" / "companyfacts.json").is_file():
        md.append("WARNING: companyfacts.json is unavailable; the XBRL sections below have no source data.")
        md.append("")
    for fam in [f[0] for f in FAMILIES] + ["shelf_fee_table"]:
        all_rows = [r for r in x if r["family"] == fam]
        rows = [r for r in all_rows if not r.get("stale")]
        md.append(f"## {fam} ({len(rows)} current facts; {len(all_rows) - len(rows)} discontinued-concept facts omitted, see CSV)")
        newest: dict = {}
        for r in rows:
            k = (r["concept"], r["unit"])
            if k not in newest or (r["end"], r["start"]) > (newest[k]["end"], newest[k]["start"]):
                newest[k] = r
        for (c, u), r in sorted(newest.items()):
            md.append(f"- {c} [{u}] = {r['value']} ({r['start'] + ' to ' if r['start'] else 'at '}{r['end']}; {r['form']} filed {r['filed']}, {r['accession']})")
        if not rows:
            md.append("- none in this folder's facts (not proof the item does not exist: check the filings)")
        md.append("")
    md.append(f"## Offering terms found by pattern ({len(o)} hits in {len({r['accession'] for r in o})} filings; see offerings.csv)")
    for r in o[:60]:
        md.append(f"- {r['filed']} {r['form']} {r['field']}: {r['value']} (line {r['line']}, {r['file']})")
    write_atomic(out / "obligations_xbrl.md", "\n".join(md) + "\n")
    print({"xbrl_facts": len(x), "offering_hits": len(o)})


if __name__ == "__main__":
    main()
