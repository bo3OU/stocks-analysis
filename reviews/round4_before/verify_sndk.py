#!/usr/bin/env python3
"""Regression check: does research/SNDK contain the facts we verified by hand on 2026-11-05/06?

Usage: .venv/bin/python scripts/verify_sndk.py [research_dir]
These are point-in-time facts about SanDisk (from its filings and FINRA). A FAIL means the fetch/parse pipeline broke
(or Finviz/FINRA changed), not that SanDisk changed. Secrets check: the Finviz token must not appear anywhere on disk.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_env  # noqa: E402

base = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "research") / "SNDK"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))


def rows(p):
    return list(csv.DictReader(open(p))) if Path(p).exists() else []


idn = json.loads((base / "identity.json").read_text()) if (base / "identity.json").exists() else {}
check("identity: CIK 2023554, name Sandisk", idn.get("cik") == 2023554 and "sandisk" in (idn.get("name") or "").lower(), str(idn.get("cik")))

idx = rows(base / "filings_index.csv")
check("index: 10-K filed 2026-08-17", any(r["form"] == "10-K" and r["filingDate"] == "2026-08-17" for r in idx))
check("index: 10-Q filed 2026-10-30", any(r["form"] == "10-Q" and r["filingDate"] == "2026-10-30" for r in idx))

q = [p for p in (base / "text").glob("2026-10-30_10-Q_*.txt")] if (base / "text").exists() else []
txt = q[0].read_text() if q else ""
check("10-Q text exists with SOURCE header", txt.startswith("# SOURCE: https://www.sec.gov/Archives/"), str(len(txt)))
check("10-Q text: revenue by geography Asia 7,216", "Asia | 7,216" in txt)
check("10-Q text: inline-XBRL header junk removed", "us-gaap:RevolvingCreditFacilityMember" not in txt)
check("10-Q text: revenue 11,031", "11,031" in txt)

ex = [p for p in (base / "text").glob("2026-10-29_8-K_*ex991*.txt")] if (base / "text").exists() else []
check("8-K 2026-10-29 EX-99.1 earnings release converted", bool(ex) and "Fiscal First Quarter 2027" in ex[0].read_text())

st = {r["Period"]: r for r in rows(base / "raw/finviz/statements_IQ.csv")}
last_col = [k for k in (next(iter(rows(base / "raw/finviz/statements_IQ.csv")), {})) if k.startswith("Q")]
c = "Q1 2027"
check("Finviz quarterly statements: Q1 2027 revenue 11,031,000,000",
      st.get("Total Revenue", {}).get(c) == "11031000000", str(st.get("Total Revenue", {}).get(c)))
check("Finviz quarterly statements: net income 8,101,000,000", st.get("Net Income", {}).get(c) == "8101000000")
check("Finviz quarterly statements: diluted EPS 52.60", st.get("EPS (Diluted)", {}).get(c) in ("52.6", "52.60"))

ins = rows(base / "derived/insider_filings.csv")
check("Form 4: CLO sale 600 sh @1158.26 on 2026-11-02 under 10b5-1",
      any("Shek" in r.get("owner", "") and r.get("date") == "2026-11-02" and r.get("code") == "S" and r.get("shares") in ("600", "600.0")
          and r.get("price") == "1158.26" and r.get("rule_10b5_1") in ("1", "true") for r in ins))
f144 = rows(base / "derived/form144_notices.csv")
check("Form 144: Goeckeler 33,841 units (filed 2026-09-17)",
      any("GOECKELER" in r.get("person", "").upper() and r.get("units_to_sell") == "33841" for r in f144))
g = rows(base / "derived/ownership_13dg.csv")
check("13D/G: BlackRock row with a percent of class", any("blackrock" in r.get("reporting_person", "").lower() and r.get("percent_of_class") for r in g))

ev = rows(base / "derived/earnings_events.csv")
check("earnings event 2026-10-29 after close, reaction -13.47%",
      any(r["filed"] == "2026-10-29" and r["session"] == "after-close" and abs(float(r["return_pct"]) + 13.47) < 0.02 for r in ev))

si = rows(base / "raw/finviz/short_interest_history.csv")
check("Finviz short-interest history: 2026-10-15 = 4,704,783",
      any(r["Settlement Date"] == "2026-10-15" and r["Short Interest"] == "4704783" for r in si))
fr = rows(base / "derived/finra_short_interest_latest.csv")
check("FINRA latest short-interest row present for SNDK", bool(fr), "no row")
if fr:
    print(f"      FINRA latest settlement {fr[0].get('settlementDate')}: {fr[0].get('currentShortPositionQuantity')} shares short")
rs = rows(base / "derived/finra_regsho_daily.csv")
check("FINRA Reg SHO daily rows present (>= 10 days)", len(rs) >= 10, str(len(rs)))

tok = load_env().get("FINVIZ_AUTH_TOKEN", "")
leaks = []
if tok:
    for p in base.rglob("*"):
        if p.is_file() and tok.encode() in p.read_bytes():
            leaks.append(str(p.relative_to(base)))
check("secrets: Finviz token appears nowhere under research/SNDK", not leaks, ", ".join(leaks[:5]))

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
