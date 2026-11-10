#!/usr/bin/env python3
"""Fetch everything the research agents need for one company into research/<TICKER>/ (deterministic, cached).

Usage:  .venv/bin/python scripts/fetch_company.py SNDK [--only sec,insiders,finviz,finra,macro,derived]
                                                     [--refresh] [--cik 2023554] [--max-insider 400] [--max-8k 60]

Layout:  research/<TICKER>/raw/{sec,finviz}/...   original files, unchanged
         research/<TICKER>/text/...               plain-text versions of filings (header lines start with '#')
         research/<TICKER>/derived/...            CSVs parsed or computed from raw files (method in INVENTORY.md)
         research/<TICKER>/{identity.json, filings_index.csv, manifest.json, INVENTORY.md}
         research/_cache/...                      market-wide files shared by all tickers (FINRA, Treasury, SEC ticker map)

Every file is listed in manifest.json with its source URL (token redacted), retrieval time, status and size.
Nothing here interprets the data. Gaps are recorded, never filled with guesses.
"""
from __future__ import annotations

import argparse
import bisect
import calendar
import csv
import datetime as dt
import json
import re
import sys
import traceback
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import Http, Manifest, Redactor, load_env, log, utcnow_iso, ROOT  # noqa: E402
from html_to_text import convert  # noqa: E402
from sec_parsers import parse_13dg, parse_form144, parse_form345  # noqa: E402

ANNUAL = {"10-K", "10-KT", "20-F", "40-F"}
INTERIM = {"10-Q", "10-QT"}
ALL_STEPS = ["sec", "insiders", "finviz", "finra", "macro", "derived"]
NY = ZoneInfo("America/New_York")

INDEX_FIELDS = ["filingDate", "reportDate", "form", "items", "accessionNumber", "primaryDocument",
                "primaryDocDescription", "acceptanceDateTime", "isInlineXBRL"]
SKIP_NAME = re.compile(r"(^r\d+\.htm$|filingsummary\.xml$|metalinks\.json$|\.xsd$|_htm\.xml$|\.css$|\.js$|"
                       r"\.(jpg|jpeg|png|gif|svg|zip|xlsx?)$|-index(-headers)?\.html?$|\.txt$|\.xml$)", re.I)


class Ctx:
    def __init__(self, args, env):
        self.args = args
        self.ticker = args.ticker.upper().replace(".", "-")
        self.root = Path(args.out).resolve()
        self.dir = self.root / self.ticker
        self.cache = self.root / "_cache"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.redact = Redactor([env.get("FINVIZ_AUTH_TOKEN", "")])
        self.manifest = Manifest(self.ticker, self.redact)
        self.http = Http(self.manifest, env["SEC_USER_AGENT"], self.root, force=args.refresh)
        pm = self.dir / "manifest.json"
        if pm.exists():
            try:
                self.http.prev = {e["path"]: e for e in json.loads(pm.read_text()).get("entries", []) if e.get("path")}
            except Exception:  # noqa: BLE001 - a corrupt old manifest only loses carried-over headers
                pass
        self.token = env["FINVIZ_AUTH_TOKEN"]
        self.today = dt.date.today()
        self.cik: int | None = int(args.cik) if args.cik else None
        self.identity: dict = {"ticker": self.ticker}
        ip = self.dir / "identity.json"
        if ip.exists():  # keep facts learned in earlier runs (partial reruns need them, e.g. the XBRL currency)
            try:
                self.identity.update(json.loads(ip.read_text()))
            except Exception:  # noqa: BLE001
                pass
        self.rows: list[dict] = []  # merged filings index
        self.notes: list[str] = []  # human-readable gaps and caps for INVENTORY.md


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for r in rows:
            for k in r:
                if k not in fields:
                    fields.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ----------------------------------------------------------------------------- identity / SEC index
def resolve_identity(ctx: Ctx) -> None:
    if ctx.cik:
        ctx.identity.update(cik=ctx.cik)
        return
    mp = ctx.cache / "company_tickers.json"
    r = ctx.http.get("https://www.sec.gov/files/company_tickers.json", host="sec", dest=mp, kind="reference", max_age_h=24)
    if not (r.ok or r.status == "cached"):
        raise RuntimeError(f"cannot load SEC ticker map ({r.status})")
    data = json.loads(mp.read_text())
    hit = next((v for v in data.values() if v["ticker"].upper() == ctx.ticker), None)
    if not hit:
        raise RuntimeError(f"ticker {ctx.ticker} not in SEC company_tickers.json (not SEC-registered, or share-class naming; try --cik)")
    ctx.cik = int(hit["cik_str"])
    ctx.identity.update(cik=ctx.cik, sec_title=hit["title"])


def rows_from_arrays(d: dict) -> list[dict]:
    n = len(d.get("accessionNumber", []))
    return [{k: (d.get(k) or [""] * n)[i] for k in INDEX_FIELDS + ["accessionNumber"]} for i in range(n)]


def step_sec(ctx: Ctx) -> None:
    cutoff = ctx.today - dt.timedelta(days=1095)
    url = f"https://data.sec.gov/submissions/CIK{ctx.cik:010d}.json"
    r = ctx.http.get(url, host="sec", dest=ctx.dir / "raw/sec/submissions.json", kind="sec_submissions", max_age_h=6)
    if not (r.ok or r.status == "cached"):
        raise RuntimeError(f"submissions fetch failed ({r.status})")
    sub = json.loads(r.path.read_text())
    rows = rows_from_arrays(sub["filings"]["recent"])
    pages = sub["filings"].get("files", [])
    for f in pages:
        oldest = min((x["filingDate"] for x in rows if x["filingDate"]), default="9999")
        if oldest <= cutoff.isoformat():
            break
        rp = ctx.http.get(f"https://data.sec.gov/submissions/{f['name']}", host="sec",
                          dest=ctx.dir / "raw/sec" / f["name"], kind="sec_submissions_older", max_age_h=24)
        if rp.ok or rp.status == "cached":
            rows += rows_from_arrays(json.loads(rp.path.read_text()))
    rows.sort(key=lambda x: (x["filingDate"], x["accessionNumber"]), reverse=True)
    ctx.rows = rows
    write_csv(ctx.dir / "filings_index.csv", rows, INDEX_FIELDS)
    forms = {x["form"] for x in rows}
    ctx.identity.update(
        name=sub.get("name"), tickers=sub.get("tickers"), exchanges=sub.get("exchanges"), sic=sub.get("sic"),
        sic_description=sub.get("sicDescription"), fiscal_year_end_mmdd=sub.get("fiscalYearEnd"),
        state_of_incorporation=sub.get("stateOfIncorporation"), entity_type=sub.get("entityType"),
        category=sub.get("category"), former_names=sub.get("formerNames"),
        filer_type=("domestic (10-K/10-Q)" if forms & {"10-K", "10-Q"} else
                    "foreign private issuer (20-F/40-F/6-K)" if forms & {"20-F", "40-F", "6-K"} else "unknown"),
        filings_in_index=len(rows), index_oldest=min((x["filingDate"] for x in rows), default=None))

    rf = ctx.http.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ctx.cik:010d}.json", host="sec",
                      dest=ctx.dir / "raw/sec/companyfacts.json", kind="sec_xbrl_companyfacts", max_age_h=12)
    if rf.ok or rf.status == "cached":
        try:
            units: Counter = Counter()
            for tax in json.loads(rf.path.read_text()).get("facts", {}).values():
                for tag in tax.values():
                    for u in tag.get("units", {}):
                        if re.fullmatch(r"[A-Z]{3}", u):
                            units[u] += len(tag["units"][u])
            if units:
                ctx.identity["xbrl_reporting_currency"] = units.most_common(1)[0][0]
                ctx.identity["xbrl_currencies_seen"] = dict(units.most_common(4))
        except Exception as e:  # noqa: BLE001
            ctx.notes.append(f"XBRL currency not determined: {e}")
    else:
        ctx.notes.append(f"XBRL company facts not available ({rf.status}); financial data must come from filing text")

    # ---- choose filings to download
    c24 = (ctx.today - dt.timedelta(days=730)).isoformat()
    c4y = (ctx.today - dt.timedelta(days=1460)).isoformat()
    by = lambda pred, n=None: [x for x in rows if pred(x)][:n]  # rows are newest-first
    tasks: list[tuple[dict, str, str | None]] = []  # (row, role, exhibit_rule)
    annual = by(lambda x: x["form"] in ANNUAL, 3)
    tasks += [(x, "annual", None) for x in annual]
    tasks += [(x, "annual_amendment", None) for x in by(lambda x: x["form"] in {a + "/A" for a in ANNUAL} and x["filingDate"] >= c24, 3)]
    interim = by(lambda x: x["form"] in INTERIM, 8)
    tasks += [(x, "interim", None) for x in interim]
    k8_all = by(lambda x: x["form"] == "8-K" and x["filingDate"] >= c24)
    for x in k8_all[: ctx.args.max_8k]:
        items = set((x["items"] or "").split(","))
        rule = None
        if items & {"2.02", "7.01", "8.01"}:
            rule = "ex99"
        if items & {"1.01", "1.02", "2.01", "2.03", "2.04", "2.05"}:
            rule = "ex99+contracts"
        tasks.append((x, "8k", rule))
    if len(k8_all) > ctx.args.max_8k:
        ctx.notes.append(f"8-K: downloaded newest {ctx.args.max_8k} of {len(k8_all)} in the last 24 months (cap --max-8k)")
    k6 = by(lambda x: x["form"] == "6-K" and x["filingDate"] >= c24)
    tasks += [(x, "6k", "all") for x in k6[:12]]
    if len(k6) > 12:
        ctx.notes.append(f"6-K: downloaded newest 12 of {len(k6)} in the last 24 months (cap)")
    tasks += [(x, "proxy", None) for x in by(lambda x: x["form"] in ("DEF 14A", "DEFM14A"), 2)]
    n_424b2 = sum(1 for x in rows if x["form"] == "424B2" and x["filingDate"] >= c24)
    fin_re = r"^(424B[134567]|S-1|S-3|S-4|F-1|F-3|S-3ASR)$" if n_424b2 > 20 else r"^(424B\d|S-1|S-3|S-4|F-1|F-3|S-3ASR)$"
    if n_424b2 > 20:
        ctx.notes.append(f"424B2: {n_424b2} in the last 24 months (structured notes / shelf takedowns); excluded from the financing documents")
    tasks += [(x, "financing", None) for x in by(lambda x: re.match(fin_re, x["form"]) and x["filingDate"] >= c24, 6)]
    tasks += [(x, "baseline_registration", None) for x in by(lambda x: x["form"] in ("10-12B/A", "10-12B", "S-1/A", "F-1/A") and x["filingDate"] >= c4y, 2)]

    if len(annual) < 3:
        ctx.notes.append(f"annual reports: only {len(annual)} found in the SEC index (young filer, spin-off, or foreign form)")
    if len(interim) < 8 and ctx.identity["filer_type"].startswith("domestic"):
        ctx.notes.append(f"interim reports (10-Q): only {len(interim)} found in the SEC index")
    if ctx.identity["filer_type"].startswith("foreign"):
        ctx.notes.append("foreign private issuer: interim results arrive via 6-K (not item-coded); earnings events are not derived")

    log(f"[sec] downloading {len(tasks)} filings")
    for row, role, rule in tasks:
        try:
            download_filing(ctx, row, role, rule)
        except Exception as e:  # noqa: BLE001
            ctx.manifest.add(kind="step_error", source="script", note=f"filing {row['accessionNumber']}: {type(e).__name__}: {e}")


def get_doc(ctx: Ctx, row: dict, name: str, role: str) -> None:
    acc_nd = row["accessionNumber"].replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{ctx.cik}/{acc_nd}/{name}"
    dest = ctx.dir / "raw/sec/filings" / acc_nd / name
    meta = dict(form=row["form"], filed=row["filingDate"], period=row["reportDate"], accession=row["accessionNumber"], role=role)
    r = ctx.http.get(url, host="sec", dest=dest, kind=f"sec_filing_{role}", immutable=True, meta=meta)
    if r.ok:
        tdest = ctx.dir / "text" / f"{row['filingDate']}_{row['form'].replace('/', '-')}_{acc_nd}_{Path(name).stem}.txt"
        if not tdest.exists() or ctx.args.refresh:
            header = (f"# SOURCE: {url}\n# FORM: {row['form']} | FILED: {row['filingDate']} | PERIOD: {row['reportDate']} | "
                      f"ACCESSION: {row['accessionNumber']} | ROLE: {role} | ITEMS: {row['items']}\n"
                      f"# Converted from raw/sec/filings/{acc_nd}/{name}; the original is authoritative.")
            ok, note = convert(dest, tdest, header)
            if not ok:
                ctx.manifest.add(kind="text_conversion", source="script", path=str(dest.relative_to(ctx.root)), status="error", note=note)


def download_filing(ctx: Ctx, row: dict, role: str, rule: str | None) -> None:
    primary = row["primaryDocument"]
    if primary and not primary.lower().endswith(".xml"):
        get_doc(ctx, row, primary, role)
    if not rule:
        return
    acc_nd = row["accessionNumber"].replace("-", "")
    idx = ctx.http.get(f"https://www.sec.gov/Archives/edgar/data/{ctx.cik}/{acc_nd}/index.json", host="sec",
                       dest=ctx.dir / "raw/sec/filings" / acc_nd / "index.json", kind="sec_filing_index", immutable=True,
                       meta=dict(accession=row["accessionNumber"], form=row["form"]))
    if not (idx.ok or idx.status == "cached"):
        return
    names = [i["name"] for i in json.loads(idx.path.read_text()).get("directory", {}).get("item", [])]
    chosen: list[str] = []
    for n in names:
        low = n.lower()
        if n == primary or SKIP_NAME.search(low) or not low.endswith((".htm", ".html", ".pdf")):
            continue
        is99 = re.search(r"ex[-_]?99", low)
        iscon = re.search(r"ex[-_]?(10|1|2|4)\d*", low) and not is99
        if (rule in ("ex99", "ex99+contracts") and is99) or (rule == "ex99+contracts" and iscon) or rule == "all":
            chosen.append(n)
    for n in chosen[:6]:
        get_doc(ctx, row, n, role + "_exhibit")
    if len(chosen) > 6:
        ctx.notes.append(f"{row['form']} {row['filingDate']}: {len(chosen)} candidate exhibits, downloaded 6")


# ----------------------------------------------------------------------------- insiders and holders
def step_insiders(ctx: Ctx) -> None:
    """Download and parse ownership XML. The SEC index lists filings where the company is the filer OR the subject
    (a bank's 13G on other issuers, a holding company's Form 4s as a 10% owner elsewhere). Rows are therefore classified by
    the issuer named inside each filing: files without the suffix are about the target; *_other_issuers / *_target_as_*
    files hold the rest. Download is adaptive: newest first until enough target filings are found or a hard cap is hit."""
    if not ctx.rows:
        raise RuntimeError("filings index missing (run the sec step first)")
    c3 = (ctx.today - dt.timedelta(days=1095)).isoformat()
    cik = str(ctx.cik)

    def fetch_xml(x, folder):
        name = Path(x["primaryDocument"]).name
        if not name.lower().endswith(".xml"):
            return None
        acc_nd = x["accessionNumber"].replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{ctx.cik}/{acc_nd}/{name}"
        r = ctx.http.get(url, host="sec", dest=ctx.dir / "raw/sec" / folder / f"{acc_nd}.xml", kind=f"sec_{folder}", immutable=True,
                         meta=dict(form=x["form"], filed=x["filingDate"], accession=x["accessionNumber"]))
        return (r.path, url) if r.ok or r.status == "cached" else None

    def run(forms, cap_matched, max_dl, folder, parser, out_name, other_name, other_label, is_target):
        cands = [x for x in ctx.rows if x["form"] in forms and x["filingDate"] >= c3]
        tgt, oth, matched, dl, bad, done = [], [], 0, 0, 0, 0
        for x in cands:
            if matched >= cap_matched or dl >= max_dl:
                break
            done += 1
            got = fetch_xml(x, folder)
            if not got:
                continue
            dl += 1
            try:
                rows = parser(got[0], x["accessionNumber"], x["filingDate"], got[1])
            except Exception as e:  # noqa: BLE001
                bad += 1
                ctx.manifest.add(kind="parse_error", source="script", note=f"{x['accessionNumber']}: {type(e).__name__}: {e}")
                continue
            t_rows = [r for r in rows if is_target(r)]
            if t_rows:
                matched += 1
            tgt += t_rows
            oth += [r for r in rows if not is_target(r)]
        for rows_, name_ in ((tgt, out_name), (oth, other_name)):
            target_file = ctx.dir / "derived" / name_
            if rows_:
                write_csv(target_file, rows_)
            else:
                target_file.unlink(missing_ok=True)  # never leave a previous run's rows standing as if current
        ctx.notes.append(f"{', '.join(sorted(forms))} (last 3 years): {len(cands)} filings in the index; processed the newest {done}; "
                         f"{matched} were about {ctx.ticker} -> {out_name} ({len(tgt)} rows); "
                         f"{len(oth)} rows are {other_label} -> {other_name}")
        if done < len(cands):
            ctx.notes.append(f"  ... stopped after {done} of {len(cands)} (target-filing cap {cap_matched} / download cap {max_dl}); older filings not fetched")
        if bad:
            ctx.notes.append(f"{out_name}: {bad} filings failed to parse (manifest parse_error entries)")

    log("[insiders] Forms 3/4/5")
    run({"3", "3/A", "4", "4/A", "5", "5/A"}, ctx.args.max_insider, int(ctx.args.max_insider * 1.5), "insiders", parse_form345,
        "insider_filings.csv", "insider_filings_other_issuers.csv", f"filings where {ctx.ticker} is a reporting owner of another issuer",
        lambda r: r.get("issuer_cik", "").lstrip("0") == cik)
    log("[insiders] Form 144")
    run({"144", "144/A"}, 100, 150, "form144", parse_form144, "form144_notices.csv", "form144_other_issuers.csv",
        "notices for other issuers", lambda r: r.get("issuer_cik", "").lstrip("0") == cik)
    log("[insiders] Schedule 13D/G")
    run({"SCHEDULE 13G", "SCHEDULE 13G/A", "SCHEDULE 13D", "SCHEDULE 13D/A"}, 60, 400, "ownership_13dg", parse_13dg,
        "ownership_13dg.csv", "ownership_13dg_target_as_filer.csv", f"positions held by {ctx.ticker} (filer) in other issuers",
        lambda r: r.get("issuer_cik", "").lstrip("0") == cik)
    legacy = [x for x in ctx.rows if x["form"].startswith("SC 13") and x["filingDate"] >= c3]
    if legacy:
        ctx.notes.append(f"{len(legacy)} legacy 'SC 13D/G' filings in the last 3 years are listed in filings_index.csv but not parsed "
                         "(HTML/text, not XML; may be about the target or filed by it)")


# ----------------------------------------------------------------------------- Finviz Elite
def step_finviz(ctx: Ctx) -> None:
    t, tok = ctx.ticker, ctx.token
    base = "https://elite.finviz.com/export/"
    items = {"price_history_daily": f"stock?t={t}&p=d", "options_chain": f"stock?t={t}&ty=oc",
             "short_interest_history": f"stock?t={t}&ty=si", "insiders": f"insiders?t={t}&tc=7", "news": f"news?v=3&t={t}"}
    for s in ("IA", "IQ", "BA", "BQ", "CA", "CQ"):
        items[f"statements_{s}"] = f"stock?t={t}&ty=statements&s={s}"
    got = {}
    for name, q in items.items():
        got[name] = ctx.http.get(f"{base}{q}&auth={tok}", host="finviz", dest=ctx.dir / f"raw/finviz/{name}.csv",
                                 kind=f"finviz_{name}", max_age_h=6, expect="csv")
    cols = ",".join(str(i) for i in range(1, 91))
    scr = ctx.http.get(f"https://elite.finviz.com/export?v=152&t={t}&c={cols}&auth={tok}", host="finviz",
                       dest=ctx.dir / "raw/finviz/screener_row_v152.csv", kind="finviz_screener_row", max_age_h=6, expect="csv")
    if scr.ok or scr.status == "cached":
        try:
            rows = list(csv.DictReader(scr.path.open()))
            if rows:
                keep = ("Company", "Sector", "Industry", "Country", "Exchange", "Market Cap", "Employees", "IPO Date",
                        "Earnings Date", "Target Price", "Analyst Recom", "Optionable", "Shortable")
                ctx.identity["finviz_profile"] = {k: rows[0][k] for k in keep if k in rows[0]}
        except Exception as e:  # noqa: BLE001
            ctx.notes.append(f"screener row not parsed: {e}")
    disp = (got.get("statements_IA").content_disposition if got.get("statements_IA") else None)
    m = re.search(r"_([a-z]{3})_\d{2}-\d{2}-\d{4}", disp or "")
    if m:
        ctx.identity["finviz_statement_currency"] = m.group(1).upper()
        xc = ctx.identity.get("xbrl_reporting_currency")
        if xc and xc != m.group(1).upper():
            ctx.notes.append(f"CURRENCY MISMATCH: Finviz statements are in {m.group(1).upper()} but the filings report in {xc}. "
                             "Finviz converts (method undocumented); do not reconcile its figures line by line to the filings.")
    ok = [n for n, r in got.items() if r.ok or r.status == "cached"]
    if not ok:
        ctx.notes.append("Finviz returned nothing usable for this ticker (not covered, or ticker format differs); see manifest")
    for n, r in got.items():
        if n.startswith("statements_") and (r.ok or r.status == "cached") and len(r.path.read_text().splitlines()) < 3:
            ctx.notes.append(f"Finviz {n}: header only (no statement data for this ticker)")


# ----------------------------------------------------------------------------- FINRA and macro (shared cache)
def prior_weekday(d: dt.date) -> dt.date:
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def symbols(ctx: Ctx) -> set[str]:
    """Class-share tickers differ by source (FINRA writes BRK/B, others BRK.B or BRK-B)."""
    t = ctx.ticker
    return {t, t.replace("-", "."), t.replace("-", "/"), t.replace("-", "")}


def step_finra(ctx: Ctx) -> None:
    cands = []
    for back in range(0, 4):
        y, m = ctx.today.year, ctx.today.month - back
        while m < 1:
            m, y = m + 12, y - 1
        for d in (15, calendar.monthrange(y, m)[1]):
            day = prior_weekday(dt.date(y, m, d))
            if day <= ctx.today:
                cands.append(day)
    cands = sorted(set(cands), reverse=True)
    found = None
    for day in cands[:6]:
        ds = day.strftime("%Y%m%d")
        r = ctx.http.get(f"https://cdn.finra.org/equity/otcmarket/biweekly/shrt{ds}.csv", host="finra",
                         dest=ctx.cache / f"finra/shrt{ds}.csv", kind="finra_short_interest", immutable=True,
                         meta=dict(settlement_date=day.isoformat()))
        if r.ok or r.status == "cached":
            found = (day, r.path)
            break
    if found and found[0] != cands[0]:
        ctx.notes.append(f"FINRA short interest: newest expected settlement date {cands[0]} not published yet (HTTP 403/404); using {found[0]}")
    if found:
        rows = []
        with found[1].open() as f:
            for row in csv.DictReader(f, delimiter="|"):
                if row.get("symbolCode") in symbols(ctx):
                    rows.append(row)
        if rows:
            write_csv(ctx.dir / "derived/finra_short_interest_latest.csv", rows)
        else:
            (ctx.dir / "derived/finra_short_interest_latest.csv").unlink(missing_ok=True)
            ctx.notes.append(f"FINRA short interest file {found[0]} has no row for {ctx.ticker}")
    else:
        (ctx.dir / "derived/finra_short_interest_latest.csv").unlink(missing_ok=True)
        ctx.notes.append("FINRA short-interest file not found for the last 6 candidate settlement dates")
    # Reg SHO daily short-sale volume: last ~20 trading days
    out, n_files, day = [], 0, ctx.today
    for _ in range(35):
        day -= dt.timedelta(days=1)
        if day.weekday() >= 5:
            continue
        ds = day.strftime("%Y%m%d")
        r = ctx.http.get(f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ds}.txt", host="finra",
                         dest=ctx.cache / f"finra/CNMSshvol{ds}.txt", kind="finra_regsho_daily", immutable=True,
                         meta=dict(trade_date=day.isoformat()))
        if r.ok or r.status == "cached":
            n_files += 1
            with r.path.open() as f:
                for row in csv.DictReader(f, delimiter="|"):
                    if row.get("Symbol") in symbols(ctx):
                        out.append(row)
        if n_files >= 20:
            break
    if out:
        write_csv(ctx.dir / "derived/finra_regsho_daily.csv", out)
    else:
        (ctx.dir / "derived/finra_regsho_daily.csv").unlink(missing_ok=True)
    ctx.notes.append(f"FINRA Reg SHO daily short-sale volume: {n_files} daily files read, {len(out)} rows for {ctx.ticker} (trade flow, not short interest)")


def step_macro(ctx: Ctx) -> None:
    y = ctx.today.year
    ctx.http.get("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
                 f"{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv", host="treasury",
                 dest=ctx.cache / f"macro/treasury_yield_curve_{y}.csv", kind="treasury_yield_curve", max_age_h=12, expect="csv")


# ----------------------------------------------------------------------------- derived
def step_derived(ctx: Ctx) -> None:
    px_path = ctx.dir / "raw/finviz/price_history_daily.csv"
    if not ctx.rows:
        idx = ctx.dir / "filings_index.csv"
        if idx.exists():
            ctx.rows = list(csv.DictReader(idx.open()))
    if not px_path.exists() or not ctx.rows:
        ctx.notes.append("earnings events not derived (need Finviz price history and the SEC filings index)")
        return
    px = []
    for r in csv.DictReader(px_path.open()):
        px.append((dt.datetime.strptime(r["Date"], "%m/%d/%Y").date(), float(r["Close"])))
    px.sort()
    dates = [d for d, _ in px]
    out = []
    for x in ctx.rows:
        if x["form"] != "8-K" or "2.02" not in (x["items"] or "").split(","):
            continue
        acc = dt.datetime.strptime(x["acceptanceDateTime"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc).astimezone(NY)
        d, tm = acc.date(), acc.hour * 60 + acc.minute
        if tm < 570:
            session, bi, ri = "pre-market", bisect.bisect_left(dates, d) - 1, bisect.bisect_left(dates, d)
        elif tm >= 960:
            session, bi, ri = "after-close", bisect.bisect_right(dates, d) - 1, bisect.bisect_right(dates, d)
        else:
            session, bi, ri = "intraday", bisect.bisect_left(dates, d) - 1, bisect.bisect_left(dates, d)
        if bi < 0 or ri >= len(dates):
            continue
        out.append(dict(filed=x["filingDate"], accepted_et=acc.strftime("%Y-%m-%d %H:%M"), session=session,
                        base_date=dates[bi], base_close=px[bi][1], reaction_date=dates[ri], reaction_close=px[ri][1],
                        return_pct=round((px[ri][1] / px[bi][1] - 1) * 100, 2), accession=x["accessionNumber"],
                        method="close-to-close around the first session after the 8-K item 2.02 acceptance time; "
                               "not a causal attribution; price basis per Finviz (adjustment undocumented)"))
    if out:
        write_csv(ctx.dir / "derived/earnings_events.csv", out)
    else:
        (ctx.dir / "derived/earnings_events.csv").unlink(missing_ok=True)
        ctx.notes.append("no earnings events derived (no 8-K item 2.02 within the price history)")


# ----------------------------------------------------------------------------- reporting
def write_inventory(ctx: Ctx, steps_run: list[str], errors: list[str]) -> None:
    ents = ctx.manifest.entries
    by_kind: dict[str, Counter] = {}
    for e in ents:
        by_kind.setdefault(e["kind"], Counter())[e.get("status", "?")] += 1
    L = [f"# Inventory: {ctx.ticker}", "", f"Generated {utcnow_iso()} by scripts/fetch_company.py. Steps run: {', '.join(steps_run)}.", ""]
    idn = ctx.identity
    L += ["## Identity", ""] + [f"- {k}: {v}" for k, v in idn.items() if v not in (None, "", [])] + [""]
    c12 = (ctx.today - dt.timedelta(days=365)).isoformat()
    top = Counter(x["form"] for x in ctx.rows if x["filingDate"] >= c12).most_common(8)
    if top:
        L += ["## SEC index: most frequent forms in the last 12 months", "", ", ".join(f"{f} x{n}" for f, n in top), ""]
    L += ["## Files by kind and status", "", "| kind | status counts |", "|---|---|"]
    for k, c in sorted(by_kind.items()):
        L.append(f"| {k} | {', '.join(f'{s}: {n}' for s, n in c.items())} |")
    bad = [e for e in ents if e.get("status") in ("blocked", "not_found", "error", "empty", "unexpected_content")]
    L += ["", "## Failures (not retrieved)", ""]
    L += [f"- {e['kind']} {e.get('status')} HTTP {e.get('http')}: {e['url'] if 'url' in e else e.get('note')}" for e in bad[:60]] or ["- none"]
    if len(bad) > 60:
        L.append(f"- ... {len(bad) - 60} more in manifest.json")
    L += ["", "## Notes: caps, gaps, limits", ""] + [f"- {n}" for n in ctx.notes] + [f"- STEP ERROR: {e}" for e in errors]
    L += ["", "## Derived files (parsed or computed; originals are in raw/)", ""]
    for p in sorted((ctx.dir / "derived").glob("*.csv")) if (ctx.dir / "derived").exists() else []:
        with p.open(newline="") as fh:
            n_rows = sum(1 for _ in csv.reader(fh)) - 1
        L.append(f"- derived/{p.name} ({n_rows} rows)")
    L += ["", "## Not collected by this script (needs discovery or an account)", "",
          "- Earnings-call transcripts and audio, investor presentations, company IR pages (many IR sites block automation)",
          "- 13F holders of this stock (13F is filed by managers; Finviz managers export has no ticker filter)",
          "- Analyst ratings table (not in the Finviz API); consensus provenance is unknown",
          "- Industry/market series, peers' filings, geopolitical sources (research agents choose and test these)",
          "- Short-interest history older than Finviz's series; borrow fees; bond trades (no source configured)", ""]
    (ctx.dir / "INVENTORY.md").write_text("\n".join(L))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ticker")
    ap.add_argument("--out", default=str(ROOT / "research"))
    ap.add_argument("--cik")
    ap.add_argument("--only", default=",".join(ALL_STEPS))
    ap.add_argument("--refresh", action="store_true", help="ignore cached files")
    ap.add_argument("--max-insider", type=int, default=400)
    ap.add_argument("--max-8k", type=int, default=60)
    args = ap.parse_args()
    env = load_env()
    for k in ("SEC_USER_AGENT", "FINVIZ_AUTH_TOKEN"):
        if not env.get(k):
            print(f"missing {k} in {ROOT / '.env'}", file=sys.stderr)
            return 2
    steps = [s for s in args.only.split(",") if s in ALL_STEPS]
    ctx = Ctx(args, env)
    errors: list[str] = []
    try:
        resolve_identity(ctx)
    except Exception as e:  # noqa: BLE001
        errors.append(f"identity: {e}")
        ctx.manifest.save(ctx.dir / "manifest.json", {"identity": ctx.identity})
        write_inventory(ctx, [], errors)
        log(f"FAILED identity: {e}")
        return 1
    fn = {"sec": step_sec, "insiders": step_insiders, "finviz": step_finviz, "finra": step_finra, "macro": step_macro, "derived": step_derived}
    if "insiders" in steps and "sec" not in steps:  # need the index
        steps = ["sec_index_only"] + steps
    for s in steps:
        t0 = dt.datetime.now()
        log(f"[{s}] start")
        try:
            if s == "sec_index_only":
                idx = ctx.dir / "filings_index.csv"
                ctx.rows = list(csv.DictReader(idx.open())) if idx.exists() else []
                continue
            fn[s](ctx)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{s}: {type(e).__name__}: {e}")
            log(f"[{s}] ERROR {type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")
        log(f"[{s}] done in {(dt.datetime.now() - t0).seconds}s")
    # identity.json: merge with any previous run so partial reruns do not lose fields
    ip = ctx.dir / "identity.json"
    prev = json.loads(ip.read_text()) if ip.exists() else {}
    prev.update({k: v for k, v in ctx.identity.items() if v is not None})
    ip.write_text(json.dumps(prev, indent=1))
    ctx.identity = prev
    # partial runs (--only ...) must not forget files fetched by earlier runs: carry over entries whose files still exist
    new_paths = {e.get("path") for e in ctx.manifest.entries if e.get("path")}
    for path, old_e in ctx.http.prev.items():
        if path not in new_paths and (ctx.root / path).exists():
            ctx.manifest.entries.append({**old_e, "carried_over": True})
    for i, e in enumerate(ctx.manifest.entries, 1):
        e["id"] = i
    ctx.manifest.save(ctx.dir / "manifest.json", {"identity": {k: prev.get(k) for k in ("cik", "name")}, "steps": steps})
    write_inventory(ctx, steps, errors)
    n_bad = sum(1 for e in ctx.manifest.entries if e.get("status") in ("blocked", "not_found", "error"))
    log(f"DONE {ctx.ticker}: {len(ctx.manifest.entries)} manifest entries, {n_bad} blocked/not found/error, {len(errors)} step errors -> {ctx.dir}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
