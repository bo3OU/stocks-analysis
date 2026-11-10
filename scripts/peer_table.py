"""Peer comparison table from cached folders (target plus peers fetched at the same cutoff).

Outputs (target RESEARCH_DIR/tables/): peers.csv and peers.md. Per company: price, market cap and shares from the latest income
statement column, TTM flows from four consecutive discrete quarters, latest balance-sheet cash and debt, and derived ratios (CALC).
Reporting currencies are shown and never mixed; ratios are computed only inside one currency. Run folders_match.py first.
Usage: .venv/bin/python -I scripts/peer_table.py <TARGET_DIR> [PEER_DIR ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if not (HERE / "toolkit.py").is_file():
    sys.path.insert(1, str(HERE.parents[2] / "scripts"))
from build_tables import load_statement, val  # noqa: E402
from toolkit import fail, fmt, research_dir, safe_child, write_atomic, write_csv  # noqa: E402

COLS = ["ticker", "folder", "name", "currency", "latest_quarter_end", "market_cap", "shares_outstanding", "ttm_revenue", "ttm_net_income", "ttm_operating_cash_flow",
        "ttm_rd", "cash_and_st_investments", "total_debt", "net_cash", "enterprise_value", "ev_to_ttm_revenue", "revenue_growth_ttm_vs_prior_ttm", "ttm_cfo_margin", "runway_quarters_at_ttm_burn", "notes"]


def ttm(data, periods, line, offset=0):
    ps = periods[offset:offset + 4]
    if len(ps) < 4 or not all(p["end"] and p["length"].startswith("3") for p in ps) or not all(70 <= (ps[i]["end"] - ps[i + 1]["end"]).days <= 110 for i in range(3)):
        return None
    v = [val(data, line, offset + i) for i in range(4)]
    return sum(v) if all(x is not None for x in v) else None


def same_quarters(left, right, count=4):
    return len(left) >= count and len(right) >= count and all(
        left[i]["end"] is not None and left[i]["end"] == right[i]["end"] for i in range(count)
    )


def row_for(rd: Path) -> dict:
    for rel in ("identity.json", "raw/finviz", *(f"raw/finviz/statements_{s}Q.csv" for s in "IBC")):
        if safe_child(rd, rel) is None:
            fail(f"path escapes research folder: {rel}")
    try:
        ident = json.loads((rd / "identity.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        fail(f"cannot read identity.json in {rd}: {e}")
    if not isinstance(ident, dict):
        fail(f"identity.json must be an object in {rd}")
    fin = rd / "raw" / "finviz"
    qi, qb, qc = (load_statement(fin / f"statements_{s}Q.csv") for s in "IBC")
    notes = []
    r = {"ticker": ident.get("ticker", ""), "folder": rd.name, "name": ident.get("name", ""), "currency": ident.get("finviz_statement_currency") or "?"}
    if not (qi and qb and qc) or not all(s[0] for s in (qi, qb, qc)):
        return {**r, "notes": "missing quarterly statements; metrics unavailable"}
    r["latest_quarter_end"] = qi[0][0]["end"].isoformat() if qi[0][0]["end"] else ""
    mc, sh = val(qi[1], "Market Capitalization", 0), val(qi[1], "Shares Outstanding", 0)
    if mc is not None and mc < 0:
        mc = None
        notes.append("negative market cap treated as unavailable")
    if sh is not None and sh <= 0:
        sh = None
        notes.append("nonpositive shares treated as unavailable")
    r["market_cap"], r["shares_outstanding"] = mc, sh
    rev, rev_prior = ttm(qi[1], qi[0], "Total Revenue"), ttm(qi[1], qi[0], "Total Revenue", 4)
    if len(qi[0]) < 8 or not qi[0][3]["end"] or not qi[0][4]["end"] or not 70 <= (qi[0][3]["end"] - qi[0][4]["end"]).days <= 110:
        rev_prior = None
    ni, cfo, rd_ = ttm(qi[1], qi[0], "Net Income"), ttm(qc[1], qc[0], "Cash from Operating Activities"), ttm(qi[1], qi[0], "Research and Development")
    if not same_quarters(qi[0], qc[0]):
        cfo = None
        notes.append("cash-flow TTM quarters differ from income statement quarters")
    cash = val(qb[1], "Cash & Short Term Investments", 0)
    ltd, std = val(qb[1], "Long Term Debt", 0), val(qb[1], "Short Term Debt Incl. Current Port. of LT Debt", 0)
    debt = ltd + std if ltd is not None and std is not None else None
    if (ltd is not None and ltd < 0) or (std is not None and std < 0):
        debt = None
        notes.append("negative debt component; EV unavailable")
    if qi[0][0]["end"] is None or qb[0][0]["end"] is None or qb[0][0]["end"] != qi[0][0]["end"]:
        cash = debt = None
        notes.append("balance sheet and income statement dates missing or different")
    if cash is not None and cash < 0:
        cash = None
        notes.append("negative cash treated as unavailable")
    r.update({"ttm_revenue": rev, "ttm_net_income": ni, "ttm_operating_cash_flow": cfo, "ttm_rd": rd_, "cash_and_st_investments": cash, "total_debt": debt})
    if cash is not None and debt is not None:
        r["net_cash"] = cash - debt
        if mc is not None and r["currency"] != "?":
            r["enterprise_value"] = mc - (cash - debt)
    if r.get("enterprise_value") is not None and rev is not None and rev > 0:
        r["ev_to_ttm_revenue"] = r["enterprise_value"] / rev
    if rev is not None and rev_prior is not None and rev_prior > 0:
        r["revenue_growth_ttm_vs_prior_ttm"] = f"{(rev / rev_prior - 1) * 100:.1f}%"
    if rev is not None and rev > 0 and cfo is not None:
        r["ttm_cfo_margin"] = f"{cfo / rev * 100:.1f}%"
    if cfo is not None and cfo < 0 and cash is not None:
        r["runway_quarters_at_ttm_burn"] = cash / (-cfo / 4)
    if mc is None:
        notes.append("market cap missing")
    elif r["currency"] != "?":
        notes.append("Finviz market cap has no quote date; EV and multiple are indicative")
    if r["currency"] == "?":
        notes.append("Finviz statement currency unknown; EV unavailable")
    if ltd is None or std is None:
        notes.append("debt component missing; EV unavailable")
    if (ident.get("xbrl_reporting_currency") or r["currency"]) != r["currency"]:
        notes.append(f"currency mismatch Finviz {r['currency']} vs XBRL {ident.get('xbrl_reporting_currency')}")
    r["notes"] = "; ".join(notes)
    return r


def main():
    if len(sys.argv) < 2:
        fail("usage: peer_table.py <TARGET_DIR> [PEER_DIR ...]")
    dirs = [research_dir(a) for a in sys.argv[1:]]
    for d in dirs:
        for rel in ("identity.json", "asof.json"):
            if safe_child(d, rel) is None:
                fail(f"path escapes research folder: {rel}")
    if safe_child(dirs[0], "tables") is None:
        fail("tables path escapes research folder")
    ids = []
    for d in dirs:
        try:
            ident = json.loads((d / "identity.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            fail(f"cannot read identity.json in {d}: {e}")
        if not isinstance(ident, dict):
            fail(f"identity.json must be an object in {d}")
        ids.append(ident)
    stamps = []
    for d, ident in zip(dirs, ids):
        meta = d / "asof.json"
        if meta.is_file():
            try:
                asof = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                fail(f"cannot read {meta}: {e}")
            if not isinstance(asof, dict):
                fail(f"invalid as-of metadata in {d}")
            cutoff = asof.get("as_of_utc")
            if not cutoff or ident.get("mode") not in ("as_of", "as-of"):
                fail(f"invalid as-of metadata in {d}")
            stamps.append(("as_of", cutoff))
        else:
            if "_asof_" in d.name or ident.get("mode") not in ("live", None):
                fail(f"missing asof.json in {d}")
            stamps.append(("live", None))
    if len(set(stamps)) != 1:
        fail("folders have different modes or UTC cutoffs; run folders_match.py")
    rows = [row_for(d) for d in dirs]
    out = dirs[0] / "tables"
    write_csv(out / "peers.csv", COLS, [{k: (fmt(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in rows])
    md = [f"# Peer table: {rows[0]['ticker']} vs {', '.join(r['ticker'] for r in rows[1:]) or '(no peers)'}",
          "Built by scripts/peer_table.py. Finviz statement values are in full units; TTM needs four consecutive discrete quarters. EV = market cap - (cash and short-term investments - total debt), excluding leases/minorities. Compare ratios only within a currency.", "",
          "| " + " | ".join(COLS[:-1]) + " | notes |", "|" + "---|" * len(COLS)]
    for r in rows:
        md.append("| " + " | ".join((fmt(r.get(c), 2) if isinstance(r.get(c), float) else str(r.get(c, "") if r.get(c) is not None else "")).replace("|", "\\|").replace("\n", " ") for c in COLS) + " |")
    write_atomic(out / "peers.md", "\n".join(md) + "\n")
    print({"companies": len(rows)})


if __name__ == "__main__":
    main()
