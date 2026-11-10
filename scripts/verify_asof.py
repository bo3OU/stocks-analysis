#!/usr/bin/env python3
"""Point-in-time regression for the SNDK as-of folders. Builds (or reuses) two folders and checks that nothing available
only after the cutoff is inside them, and that what was available is.

  .venv/bin/python -I scripts/verify_asof.py

Cutoff A = 2026-10-29 16:00 New York: SanDisk's earnings 8-K was accepted at 16:13 and the 10-Q on 2026-10-30, so both must be absent;
the 10-29 daily close (known 16:05) must be absent too.
Cutoff B = 2026-10-29 16:30 New York: the 8-K (16:13) and the 10-29 close are now known; the 10-Q (10-30) and the 10-30 close are not.
"""
import csv
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_env  # noqa: E402
from asof import parse_as_of  # noqa: E402

RES = ROOT / "research"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))


def rows(p):
    p = Path(p)
    return list(csv.DictReader(open(p))) if p.exists() else []


def build(as_of):
    out = subprocess.run([str(ROOT / ".venv/bin/python"), "-I", str(ROOT / "scripts/fetch_company.py"), "SNDK", "--as-of", as_of, "--tz", "America/New_York"],
                         capture_output=True, text=True)
    line = [l for l in out.stdout.splitlines() if l.startswith("RESEARCH_DIR=")]
    return Path(line[0].split("=", 1)[1]) if line else None


def common_checks(d, cutoff_utc, label):
    check(f"{label}: folder built", d is not None and d.exists(), str(d))
    if d is None:
        return
    meta = json.loads((d / "asof.json").read_text())
    check(f"{label}: asof.json has the exact UTC instant", meta["as_of_utc"] == cutoff_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), meta["as_of_utc"])
    idx = rows(d / "filings_index.csv")
    late = [r for r in idx if r["acceptanceDateTime"] and dt.datetime.fromisoformat(r["acceptanceDateTime"].replace("Z", "+00:00")) > cutoff_utc]
    check(f"{label}: no filing in the index was accepted after the cutoff", not late, str(late[:1]))
    check(f"{label}: the 2026-10-30 10-Q is absent", not any(r["form"] == "10-Q" and r["filingDate"] == "2026-10-30" for r in idx))
    check(f"{label}: the 2026-05-01 10-Q is present", any(r["form"] == "10-Q" and r["filingDate"] == "2026-05-01" for r in idx))
    texts = [p.name for p in (d / "text").glob("*")] if (d / "text").exists() else []
    check(f"{label}: no converted text from 2026-10-30 or later", not any(n[:10] >= "2026-10-30" for n in texts))
    ins = rows(d / "derived/insider_filings.csv")
    check(f"{label}: no insider filing after the cutoff date", all(r["filed"] <= "2026-10-29" for r in ins) and bool(ins), str(max((r["filed"] for r in ins), default=None)))
    check(f"{label}: the 2026-11-03 Form 4 sale is absent", not any(r.get("date") == "2026-11-02" and r.get("code") == "S" for r in ins))
    facts = json.loads((d / "raw/sec/companyfacts.json").read_text())
    ends, filed = set(), set()
    for tax in facts["facts"].values():
        for tag in tax.values():
            for fl in tag["units"].values():
                for f in fl:
                    filed.add(f["filed"]); ends.add(f["end"])
    check(f"{label}: XBRL has no retrieval-time frame labels",
          all("frame" not in f for tax in facts["facts"].values() for tag in tax.values()
              for fl in tag["units"].values() for f in fl))
    check(f"{label}: XBRL facts filed after 2026-10-29 are absent", max(filed) <= "2026-10-29", max(filed))
    check(f"{label}: no XBRL fact for the quarter ended 2026-10-02 (reported 2026-10-30)", "2026-10-02" not in ends)
    check(f"{label}: XBRL facts from the 2026-04-03 quarter are present", "2026-04-03" in ends)
    si = rows(d / "raw/finviz/short_interest_history.csv")
    check(f"{label}: short-interest rows stop at 2026-10-15 or earlier", bool(si) and max(r["Settlement Date"] for r in si) <= "2026-10-15", str(max((r["Settlement Date"] for r in si), default=None)))
    for name in ("options_chain", "news", "insiders", "screener_row_v152", "statements_IA", "statements_IQ", "statements_BA", "statements_CA"):
        check(f"{label}: live Finviz snapshot {name} is not in the folder", not (d / f"raw/finviz/{name}.csv").exists())
    man = json.loads((d / "manifest.json").read_text())
    check(f"{label}: manifest exposes no shared-cache path",
          all(not (e.get("path") or "").startswith("_cache/") for e in man["entries"]))
    identity = json.loads((d / "identity.json").read_text())
    check(f"{label}: current SEC identity fields are absent",
          not any(k in identity for k in ("name", "sec_title", "tickers", "exchanges", "former_names")))
    check(f"{label}: manifest records skipped live snapshots", sum(1 for e in man["entries"] if e.get("status") == "skipped_asof") >= 10)
    check(f"{label}: raw/sec has no unfiltered submissions file", not (d / "raw/sec/submissions.json").exists())
    inv = (d / "INVENTORY.md").read_text()
    check(f"{label}: INVENTORY starts with the AS-OF MODE section", "## AS-OF MODE" in inv and inv.index("## AS-OF MODE") < inv.index("## Identity"))
    tre = rows(d / "raw/macro/treasury_yield_curve.csv")
    check(f"{label}: Treasury rows stop before the cutoff date", bool(tre) and dt.datetime.strptime(tre[0]["Date"], "%m/%d/%Y").date() < dt.date(2026, 10, 29), tre[0]["Date"] if tre else "none")
    fin = rows(d / "derived/finra_short_interest_latest.csv")
    check(f"{label}: FINRA short-interest row settlement <= 2026-10-15", bool(fin) and fin[0]["settlementDate"] <= "2026-10-15", str(fin[:1]))
    rs = rows(d / "derived/finra_regsho_daily.csv")
    check(f"{label}: Reg SHO rows are dated before the cutoff date", all(r["Date"] < "20261029" for r in rs) and bool(rs), str(max((r["Date"] for r in rs), default=None)))


A = dt.datetime(2026, 10, 29, 20, 0, tzinfo=dt.timezone.utc)  # 16:00 EDT
B = dt.datetime(2026, 10, 29, 20, 30, tzinfo=dt.timezone.utc)  # 16:30 EDT
dA = build("2026-10-29 16:00")
common_checks(dA, A, "A 16:00")
if dA:
    before_meta = (dA / "asof.json").read_bytes()
    partial = subprocess.run([str(ROOT / ".venv/bin/python"), "-I", str(ROOT / "scripts/fetch_company.py"),
                              "SNDK", "--as-of", "2026-10-29 16:00", "--only", "sec"],
                             capture_output=True, text=True)
    check("A 16:00: partial as-of rerun is refused without changing the folder",
          partial.returncode != 0 and (dA / "asof.json").read_bytes() == before_meta)
    px = rows(dA / "raw/finviz/price_history_daily.csv")
    check("A 16:00: last daily row is 10/28 (the 10-29 close is known only at 16:05)", px and px[-1]["Date"] == "10/28/2026", px[-1]["Date"] if px else "none")
    ev = rows(dA / "derived/earnings_events.csv")
    check("A 16:00: the 2026-10-29 earnings event is absent", not any(r["filed"] == "2026-10-29" for r in ev))
    check("A 16:00: the earnings 8-K accepted at 16:13 is absent", not any(r["form"] == "8-K" and r["filingDate"] == "2026-10-29" for r in rows(dA / "filings_index.csv")))
# agent_fetch enforcement inside the 16:00 folder
if dA:
    def af(*a):
        out = subprocess.run([str(ROOT / ".venv/bin/python"), "-I", str(ROOT / "scripts/agent_fetch.py"), *a, "--ticker", dA.name,
                              "--agent", "stock-filings-reader"], capture_output=True, text=True)
        try:
            return json.loads(out.stdout.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            return {"status": "no-json", "error": out.stdout[-200:] + out.stderr[-200:]}
    dl = f"research/{dA.name}/agents/stock-filings-reader/work/downloads"
    idxrows = rows(dA / "filings_index.csv")
    ok_acc = next(r["accessionNumber"] for r in idxrows if r["form"] == "10-Q").replace("-", "")
    r = af("sec", f"https://www.sec.gov/Archives/edgar/data/2023554/{ok_acc}/index.json", "--out", f"{dl}/ok.json")
    check("A 16:00 agent_fetch: a filing in the index can be fetched", r.get("status") in ("ok", "cached"), str(r))
    r = af("sec", "https://www.sec.gov/Archives/edgar/data/2023554/000162828026068601/sndk-20261002.htm", "--out", f"{dl}/late.htm")
    check("A 16:00 agent_fetch: a filing accepted after the cutoff is refused", r.get("status") == "refused", str(r))
    r = af("sec", "https://data.sec.gov/api/xbrl/companyfacts/CIK0002023554.json", "--out", f"{dl}/cf.json")
    check("A 16:00 agent_fetch: the live XBRL listing is refused", r.get("status") == "refused", str(r))
    r = af("sec", "https://www.sec.gov/files/company_tickers.json", "--out", f"{dl}/tickers.json")
    check("A 16:00 agent_fetch: current SEC ticker map is refused", r.get("status") == "refused", str(r))
    r = af("finviz", "export/stock?t=SNDK&ty=oc", "--out", f"{dl}/oc.csv")
    check("A 16:00 agent_fetch: a live Finviz snapshot (options) is refused", r.get("status") == "refused", str(r))
    r = af("finviz", "export/stock?t=SPY&p=d", "--out", f"{dl}/spy.csv")
    spy = rows(ROOT / f"{dl}/spy.csv")
    check("A 16:00 agent_fetch: a benchmark price history is cut at the cutoff", r.get("status") == "ok" and spy and spy[-1]["Date"] == "10/28/2026", str(r)[:160])
    check("A 16:00 agent_fetch: no unfiltered file is left behind", not list((ROOT / dl).glob("*.unfiltered")))
    import shutil
    shutil.rmtree(dA / "agents", ignore_errors=True)

dB = build("2026-10-29 16:30")
common_checks(dB, B, "B 16:30")
if dB:
    px = rows(dB / "raw/finviz/price_history_daily.csv")
    check("B 16:30: last daily row is 10/29 (close known)", px and px[-1]["Date"] == "10/29/2026", px[-1]["Date"] if px else "none")
    check("B 16:30: the earnings 8-K accepted at 16:13 is present", any(r["form"] == "8-K" and r["filingDate"] == "2026-10-29" for r in rows(dB / "filings_index.csv")))
    check("B 16:30: its release text was converted", any("2026-10-29_8-K" in p.name for p in (dB / "text").glob("*")))
    ev = rows(dB / "derived/earnings_events.csv")
    check("B 16:30: the 2026-10-29 event is still absent (the 10-30 reaction close is unknown)", not any(r["filed"] == "2026-10-29" for r in ev))

ambiguous_refused = False
try:
    parse_as_of("2026-11-01 01:30")
except ValueError:
    ambiguous_refused = True
check("DST: ambiguous New York wall time is refused", ambiguous_refused)

# input rules and folder comparison
def fc(*a):
    return subprocess.run([str(ROOT / ".venv/bin/python"), "-I", str(ROOT / "scripts/fetch_company.py"), "SNDK", *a], capture_output=True, text=True)
check("as-of with a naive time and no --tz is rejected", fc("--as-of", "2026-10-29 16:00").returncode == 2)
check("as-of with a date only is rejected", fc("--as-of", "2026-10-29", "--tz", "America/New_York").returncode == 2)
check("as-of with seconds is rejected", fc("--as-of", "2026-10-29 16:00:30", "--tz", "America/New_York").returncode == 2)
check("as-of with --only is rejected", fc("--as-of", "2026-10-29 16:00", "--tz", "America/New_York", "--only", "sec").returncode == 2)
fm = lambda *a: json.loads(subprocess.run([str(ROOT / ".venv/bin/python"), "-I", str(ROOT / "scripts/folders_match.py"), *a], capture_output=True, text=True).stdout)
if dA and dB:
    check("folders_match: two folders with the same cutoff match", fm(str(dA), str(dA))["ok"])
    check("folders_match: different cutoffs do not match", not fm(str(dA), str(dB))["ok"])
    check("folders_match: an as-of folder and a live folder do not match", not fm(str(dA), str(RES / "SNDK"))["ok"])

tok = load_env().get("FINVIZ_AUTH_TOKEN", "")
leaks = [str(p) for d in (dA, dB) if d for p in d.rglob("*") if p.is_file() and tok.encode() in p.read_bytes()] if tok else []
check("secrets: token appears nowhere in the as-of folders", not leaks, str(leaks[:2]))
print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
