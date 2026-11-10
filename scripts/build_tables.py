"""Financial tables from the cached Finviz statements and SEC XBRL company facts, for the financials/valuation agents.

Outputs (RESEARCH_DIR/tables/): statements_long.csv (annual+quarterly, history-limited), xbrl_quarterly.csv (discrete quarters,
YTD facts differenced), xbrl_instants.csv, reconciliation.csv (Finviz vs XBRL for key lines), financial_summary.md (wide key lines,
TTM, cash runway arithmetic). All numbers are CALC from cached files; nothing is estimated. Uses only this folder's files.
Usage: .venv/bin/python -I scripts/build_tables.py <TICKER or RESEARCH_DIR> [--history-years 5]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if not (HERE / "toolkit.py").is_file():
    sys.path.insert(1, str(HERE.parents[2] / "scripts"))
from toolkit import fail, fmt, num, parse_date, research_dir, safe_child, write_atomic, write_csv  # noqa: E402

KEY_LINES = {
    "I": ["Total Revenue", "Gross Profit", "Research and Development", "Selling, General and Administrative Excl. Other", "Operating Income", "Net Income", "EPS (Diluted)", "EBITDA", "Stock Option Compensation Expense", "Shares Outstanding", "Market Capitalization"],
    "B": ["Cash & Short Term Investments", "Total Current Assets", "Total Assets", "Short Term Debt Incl. Current Port. of LT Debt", "Long Term Debt", "Total Liabilities", "Total Shareholders Equity"],
    "C": ["Cash from Operating Activities", "Capital Expenditures", "Free Cash Flow", "Purchase or Sale of Investments", "Sale of Common Pref Stock", "Issuance of Long Term Debt", "Cash from Financing Activities", "Net Change in Cash"],
}
FLOW_LINES = {"Total Revenue", "Gross Profit", "Research and Development", "Selling, General and Administrative Excl. Other", "Operating Income", "Net Income", "EBITDA", "Stock Option Compensation Expense",
              "Cash from Operating Activities", "Capital Expenditures", "Free Cash Flow", "Sale of Common Pref Stock", "Issuance of Long Term Debt", "Cash from Financing Activities", "Net Change in Cash", "Purchase or Sale of Investments"}
STMT_NAME = {"I": "income", "B": "balance", "C": "cashflow"}
XBRL_FLOW = ["NetCashProvidedByUsedInOperatingActivities", "NetIncomeLoss", "ResearchAndDevelopmentExpense", "SellingGeneralAndAdministrativeExpense", "OperatingIncomeLoss",
             "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "ShareBasedCompensation", "ProceedsFromIssuanceOfCommonStock", "StockIssuedDuringPeriodValueNewIssues",
             "NetCashProvidedByUsedInFinancingActivities", "PaymentsToAcquirePropertyPlantAndEquipment"]
XBRL_INSTANT = ["CashAndCashEquivalentsAtCarryingValue", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "ShortTermInvestments", "LongTermDebt",
                "ConvertibleNotesPayable", "LongTermDebtNoncurrent", "StockholdersEquity", "Assets", "Liabilities", "CommonStockSharesOutstanding"]
RECON = [("Cash from Operating Activities", "NetCashProvidedByUsedInOperatingActivities"), ("Net Income", "NetIncomeLoss"), ("Research and Development", "ResearchAndDevelopmentExpense")]


def load_statement(path: Path):
    if not path.is_file():
        return None
    import csv
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2 or not rows[0] or rows[0][0] != "Period" or not rows[1] or rows[1][0] != "Period End Date":
        fail(f"invalid statement headers: {path}")
    if len(rows[0]) != len(rows[1]) or len(rows[0]) < 2:
        fail(f"misaligned statement periods: {path}")
    periods = [{"label": rows[0][i], "end": parse_date(rows[1][i]) if i < len(rows[1]) else None, "length": ""} for i in range(1, len(rows[0]))]
    undated = [p["label"] for p in periods if p["end"] is None and not p["label"].strip().upper().startswith("TTM")]
    if undated:  # TTM columns carry no end date by design; a young company can have undated old columns: those are left out, not guessed
        print(f"WARNING: {path.name}: columns without a period end date are excluded: {', '.join(undated)}", file=sys.stderr)
    for r in rows[2:]:
        if r and r[0] == "Period Length":
            for i, p in enumerate(periods):
                p["length"] = r[i + 1] if i + 1 < len(r) else ""
    data = {}
    excluded = set()
    for r in rows[2:]:
        if not r or r[0] in ("Period Length", "Period End Date"):
            continue
        if not r[0].strip() or r[0] in excluded:
            continue
        if r[0] in data:
            if data[r[0]] == r[1:]:
                print(f"WARNING: {path.name}: identical duplicate statement line {r[0]!r} ignored", file=sys.stderr)
            else:
                print(f"WARNING: {path.name}: conflicting statement line {r[0]!r} excluded", file=sys.stderr)
                del data[r[0]]
                excluded.add(r[0])
            continue
        data[r[0]] = r[1:]
    return periods, data


def val(data, line, i):
    r = data.get(line)
    v = num(r[i]) if r and i < len(r) else None
    return v if v is None or math.isfinite(v) else None


def recon_close(finviz: float, xbrl: float) -> bool:
    tolerance = min(max(0.005 * abs(xbrl), 1000), 0.05 * max(abs(finviz), abs(xbrl)))
    return abs(finviz - xbrl) <= tolerance


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--history-years", type=int, default=5)
    a = ap.parse_args()
    if a.history_years < 1:
        fail("--history-years must be positive")
    rd = research_dir(a.folder)
    fin = rd / "raw" / "finviz"
    if safe_child(rd, "identity.json") is None or safe_child(rd, "raw/finviz") is None or safe_child(rd, "raw/sec/companyfacts.json") is None or safe_child(rd, "tables") is None:
        fail("research folder contains a path escaping the folder")
    for freq in ("A", "Q"):
        for st in ("I", "B", "C"):
            if safe_child(rd, f"raw/finviz/statements_{st}{freq}.csv") is None:
                fail("statement path escapes the research folder")
    try:
        ident = json.loads((rd / "identity.json").read_text(encoding="utf-8"))
        if not isinstance(ident, dict):
            fail("identity.json must be an object")
    except (OSError, ValueError) as e:
        fail(f"cannot read identity.json: {e}")
    long_rows, wide = [], {}
    latest_end = None
    for freq in ("A", "Q"):
        for st in ("I", "B", "C"):
            s = load_statement(fin / f"statements_{st}{freq}.csv")
            if not s:
                continue
            periods, data = s
            ends = [p["end"] for p in periods if p["end"]]
            if ends:
                latest_end = max(latest_end or max(ends), max(ends))
            limit = (max(ends) - dt.timedelta(days=366 * a.history_years)) if ends else None
            wide[(freq, st)] = (periods, data)
            for line, vals in data.items():
                for i, p in enumerate(periods):
                    if p["end"] and limit and p["end"] >= limit and i < len(vals) and vals[i] != "":
                        long_rows.append({"freq": "ttm" if p["label"] == "TTM" else ("annual" if freq == "A" else "quarterly"), "statement": STMT_NAME[st], "line_item": line, "period": p["label"],
                                          "period_end": p["end"].isoformat(), "period_length": p["length"], "value": vals[i]})
    cf = rd / "raw" / "sec" / "companyfacts.json"
    if not wide and not cf.is_file():
        fail("no Finviz statements or SEC companyfacts in this research folder")
    out = rd / "tables"
    # XBRL
    qrows, irows, recon = [], [], []
    xq: dict[tuple, dict] = {}
    if cf.is_file():
        try:
            document = json.loads(cf.read_text(encoding="utf-8", errors="replace"),
                                  parse_constant=lambda x: fail(f"nonfinite JSON number in companyfacts: {x}"))
        except (OSError, ValueError) as e:
            fail(f"cannot read companyfacts.json: {e}")
        if not isinstance(document, dict):
            fail("companyfacts.json must be an object")
        facts = document.get("facts", {})
        if not isinstance(facts, dict) or not isinstance(facts.get("us-gaap", {}), dict):
            fail("companyfacts.json has invalid facts/us-gaap data")
        us = facts.get("us-gaap", {})
        if latest_end is None:
            available_ends = [parse_date(f.get("end")) for tag in XBRL_FLOW + XBRL_INSTANT for fl in us.get(tag, {}).get("units", {}).values() for f in fl if f.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "20-F/A", "6-K")]
            latest_end = max((e for e in available_ends if e), default=None)
        limit = (latest_end - dt.timedelta(days=366 * a.history_years)) if latest_end else None
        for tag in XBRL_FLOW:
            body = us.get(tag)
            if not body:
                continue
            for unit, fl in body.get("units", {}).items():
                dur = {}
                for f in fl:
                    s_, e_ = parse_date(f.get("start")), parse_date(f.get("end"))
                    if s_ and e_ and f.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "20-F/A", "6-K"):
                        k = (s_, e_)
                        if k not in dur or (f.get("filed") or "", f.get("accn") or "") > (dur[k].get("filed") or "", dur[k].get("accn") or ""):
                            dur[k] = f
                by_start: dict = {}
                for (s_, e_), f in dur.items():
                    by_start.setdefault(s_, []).append((e_, f))
                disc = {}
                ranks = {}
                def consider(end, value, fact, how, start):
                    if value is None or not math.isfinite(value):
                        return
                    rank = (how == "reported 3-month", fact.get("filed") or "", fact.get("accn") or "", start.isoformat())
                    if end not in ranks or rank > ranks[end]:
                        disc[end] = (value, fact, how)
                        ranks[end] = rank
                for s_, lst in by_start.items():
                    lst.sort(key=lambda x: x[0])
                    for e_, f in lst:
                        if 70 <= (e_ - s_).days <= 110:
                            consider(e_, num(f.get("val")), f, "reported 3-month", s_)
                    for (e1, f1), (e2, f2) in zip(lst, lst[1:]):
                        v1, v2 = num(f1.get("val")), num(f2.get("val"))
                        if 70 <= (e2 - e1).days <= 110 and v1 is not None and v2 is not None:
                            consider(e2, v2 - v1, f2, f"YTD to {e2} minus YTD to {e1}", s_)
                for e_, (v, f, how) in sorted(disc.items()):
                    if v is None or not math.isfinite(v) or (limit and e_ < limit):
                        continue
                    if unit == ident.get("finviz_statement_currency") and unit == ident.get("xbrl_reporting_currency"):
                        xq[(tag, e_)] = {"v": v, "unit": unit}
                    qrows.append({"concept": tag, "unit": unit, "quarter_end": e_.isoformat(), "value": fmt(v, 0) if v is not None else "", "method": how,
                                  "fy": f.get("fy"), "fp": f.get("fp"), "form": f.get("form"), "filed": f.get("filed"), "accession": f.get("accn")})
        for tag in XBRL_INSTANT:
            body = us.get(tag)
            if not body:
                continue
            for unit, fl in body.get("units", {}).items():
                best = {}
                for f in fl:
                    e_ = parse_date(f.get("end"))
                    if e_ and f.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "20-F/A", "6-K") and (not limit or e_ >= limit):
                        if e_ not in best or (f.get("filed") or "", f.get("accn") or "") > (best[e_].get("filed") or "", best[e_].get("accn") or ""):
                            best[e_] = f
                for e_, f in sorted(best.items()):
                    v = num(f.get("val"))
                    if v is None or not math.isfinite(v):
                        continue
                    irows.append({"concept": tag, "unit": unit, "as_of": e_.isoformat(), "value": f.get("val"), "fy": f.get("fy"), "fp": f.get("fp"), "form": f.get("form"), "filed": f.get("filed"), "accession": f.get("accn")})
    write_csv(out / "statements_long.csv", ["freq", "statement", "line_item", "period", "period_end", "period_length", "value"], long_rows)
    write_csv(out / "xbrl_quarterly.csv", ["concept", "unit", "quarter_end", "value", "method", "fy", "fp", "form", "filed", "accession"], qrows)
    write_csv(out / "xbrl_instants.csv", ["concept", "unit", "as_of", "value", "fy", "fp", "form", "filed", "accession"], irows)
    # reconciliation: Finviz quarterly vs XBRL discrete quarters
    for fv_line, tag in RECON:
        for st in (("C",) if fv_line == "Cash from Operating Activities" else ("I",)):
            s = wide.get(("Q", st))
            if not s or fv_line not in s[1]:
                continue
            periods, data = s
            for i, p in enumerate(periods[:8]):
                if not p["length"].startswith("3"):
                    continue
                fv = val(data, fv_line, i)
                xv = xq.get((tag, p["end"]), {}).get("v") if p["end"] else None
                if not ident.get("finviz_statement_currency") or not ident.get("xbrl_reporting_currency"):
                    status = "currency unknown"
                    xv = None
                elif ident["finviz_statement_currency"] != ident["xbrl_reporting_currency"]:
                    status = "currency mismatch"
                    xv = None
                elif fv is None or xv is None:
                    status = "no XBRL quarter" if fv is not None else "no Finviz value"
                else:
                    flip = recon_close(abs(fv), abs(xv))
                    status = "match" if recon_close(fv, xv) else ("match up to sign" if flip else "MISMATCH")
                recon.append({"line_item": fv_line, "xbrl_concept": tag, "period_end": p["end"].isoformat() if p["end"] else "", "finviz": fmt(fv, 0) if fv is not None else "",
                              "xbrl": fmt(xv, 0) if xv is not None else "", "status": status})
    write_csv(out / "reconciliation.csv", ["line_item", "xbrl_concept", "period_end", "finviz", "xbrl", "status"], recon)
    write_atomic(out / "financial_summary.md", summary(rd, ident, wide, a.history_years, recon, qrows, irows))
    print({"statement_rows": len(long_rows), "xbrl_quarters": len(qrows), "xbrl_instants": len(irows), "recon_rows": len(recon)})


def summary(rd, ident, wide, years, recon, qrows=None, irows=None) -> str:
    o = [f"# Financial summary: {ident.get('ticker', rd.name)} ({ident.get('name', '')})",
         f"Built by scripts/build_tables.py from raw/finviz/statements_*.csv and raw/sec/companyfacts.json; history window {years} years; values as stored (see currency line and CSV unit columns).",
         f"Currency: Finviz statements {ident.get('finviz_statement_currency', '?')}, XBRL {ident.get('xbrl_reporting_currency', '?')}"
         + ("  **MISMATCH: do not mix them**" if ident.get("finviz_statement_currency") and ident.get("xbrl_reporting_currency") and ident["finviz_statement_currency"] != ident["xbrl_reporting_currency"] else ""), ""]
    if not wide:
        o.append("Finviz statements are unavailable in this folder; XBRL tables below are limited to cached facts. No Finviz TTM or runway is computed.")
        o.append(f"- XBRL discrete quarter rows: {len(qrows or [])}; see xbrl_quarterly.csv and xbrl_instants.csv")
        currencies = {r["unit"] for r in (qrows or []) + (irows or []) if r["unit"] != "shares"}
        preferred = ident.get("xbrl_reporting_currency") or (next(iter(currencies)) if len(currencies) == 1 else None)
        if preferred is None and currencies:
            o.append("- Reporting currency is unknown or multiple currencies occur; inspect XBRL CSV unit columns before using values.")
        o.append("## Latest cached XBRL facts")
        if not qrows and not irows:
            o.append("- No supported us-gaap facts in the cached companyfacts; inspect the issuer's reporting taxonomy.")
        for rows, date_key, concepts in ((qrows or [], "quarter_end", ("NetCashProvidedByUsedInOperatingActivities", "NetIncomeLoss", "ResearchAndDevelopmentExpense", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")),
                                         (irows or [], "as_of", ("CashAndCashEquivalentsAtCarryingValue", "MarketableSecuritiesCurrent", "ShortTermInvestments", "LongTermDebt", "LongTermDebtNoncurrent", "ConvertibleNotesPayable", "CommonStockSharesOutstanding"))):
            for concept in concepts:
                candidates = [r for r in rows if r["concept"] == concept and r["unit"] in (preferred, "shares")]
                if candidates:
                    r = max(candidates, key=lambda row: (row[date_key], row.get("filed") or ""))
                    o.append(f"- {concept} {r[date_key]}: {r['value']} {r['unit']} ({r.get('form') or '?'}, filed {r.get('filed') or '?'})")
        o.append("")
    for freq, title, n in (("A", "Annual", years), ("Q", "Quarterly (latest 8)", 8)):
        o.append(f"## {title}")
        for st in ("I", "B", "C"):
            s = wide.get((freq, st))
            if not s:
                continue
            periods, data = s
            k = min(len(periods), n if freq == "Q" else n)
            if freq == "A" and periods and periods[0]["label"] == "TTM":
                k = min(len(periods), n + 1)
            cols = [p["label"] for p in periods[:k]]
            o.append(f"### {STMT_NAME[st].title()}")
            o.append("| line | " + " | ".join(cols) + " |")
            o.append("|---|" + "---|" * len(cols))
            for line in KEY_LINES[st]:
                if line in data:
                    nd = 2 if line == "EPS (Diluted)" else 0
                    o.append(f"| {line} | " + " | ".join(fmt(val(data, line, i), nd) if val(data, line, i) is not None else "" for i in range(k)) + " |")
        o.append("")
    # TTM and runway from quarterly statements
    qi, qb, qc = wide.get(("Q", "I")), wide.get(("Q", "B")), wide.get(("Q", "C"))
    o.append("## TTM and cash runway (CALC)")
    if qc and qc[0]:
        periods, data = qc
        ends = [p["end"] for p in periods[:4]]
        consecutive = len(ends) == 4 and all(e for e in ends) and all(70 <= (ends[i] - ends[i + 1]).days <= 110 for i in range(3)) and all(p["length"].startswith("3") for p in periods[:4])
        if consecutive:
            for line in ("Cash from Operating Activities", "Free Cash Flow", "Cash from Financing Activities"):
                v = [val(data, line, i) for i in range(4)]
                if all(x is not None for x in v):
                    o.append(f"- TTM {line} = {fmt(sum(v), 0)} (sum of quarters ending {', '.join(e.isoformat() for e in reversed(ends))})")
        else:
            o.append("- TTM not computed: last four cash-flow columns are not four consecutive discrete quarters")
        cfo = [val(data, "Cash from Operating Activities", i) for i in range(4)]
        cash_date = qb[0][0]["end"] if qb and qb[0] else None
        cfo_date = periods[0]["end"] if periods else None
        if qb and cash_date is not None and cash_date == cfo_date and val(qb[1], "Cash & Short Term Investments", 0) is not None and cfo[0] is not None and periods[0]["length"].startswith("3"):
            cash = val(qb[1], "Cash & Short Term Investments", 0)
            if cash < 0:
                o.append("- Latest cash and short-term investments is negative; runway unavailable")
            else:
                o.append(f"- Latest cash and short-term investments {fmt(cash, 0)} at {qb[0][0]['end']}")
                if cfo[0] < 0:
                    o.append(f"- Runway at latest-quarter operating cash use ({fmt(-cfo[0], 0)}): {cash / -cfo[0]:.1f} quarters = cash / quarterly operating cash use; ignores financing, investing and any burn change")
                if consecutive and all(x is not None for x in cfo) and sum(cfo) < 0:
                    o.append(f"- Runway at TTM average operating cash use ({fmt(-sum(cfo) / 4, 0)}): {cash / (-sum(cfo) / 4):.1f} quarters; same limits")
                if cfo[0] >= 0:
                    o.append("- Operating cash flow positive in the latest quarter: no burn runway computed")
    bad = [r for r in recon if r["status"] == "MISMATCH"]
    o += ["", "## Finviz vs XBRL reconciliation (see reconciliation.csv)",
          f"- {sum(r['status'] == 'match' for r in recon)} matches, {sum(r['status'] == 'match up to sign' for r in recon)} sign-only, {len(bad)} MISMATCH, {sum(r['status'].startswith('no ') or r['status'].startswith('currency ') for r in recon)} not comparable"]
    for r in bad[:10]:
        o.append(f"- MISMATCH {r['line_item']} {r['period_end']}: Finviz {r['finviz']} vs XBRL {r['xbrl']}")
    return "\n".join(o) + "\n"


if __name__ == "__main__":
    main()
