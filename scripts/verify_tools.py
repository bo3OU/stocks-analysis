"""Regression checks for the offline analysis scripts, on a synthetic folder (research/ZZTOOLS, removed afterwards) and,
when present, on real cached folders. Usage: .venv/bin/python -I scripts/verify_tools.py"""
from __future__ import annotations

import csv
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_HERE = HERE if (HERE / "toolkit.py").is_file() else HERE.parents[2] / "scripts"
sys.path.insert(0, str(SOURCE_HERE))
import build_digest as bd  # noqa: E402
import build_insider_ledger as bl  # noqa: E402
import toolkit as tk  # noqa: E402

PY = [sys.executable, "-I"]
FAILS, N = [], 0


def check(name, cond, detail=""):
    global N
    N += 1
    if not cond:
        FAILS.append(f"{name} {detail}")
        print(f"FAIL {name} {detail}")


def run(script, *args, inp=None):
    path = HERE / script if (HERE / script).is_file() else SOURCE_HERE / script
    return subprocess.run(PY + [str(path), *args], capture_output=True, text=True, input=inp)


def main():
    # toolkit: federal holidays and business days
    check("holiday thanksgiving 2026", dt.date(2026, 11, 26) in tk.federal_holidays(2026))
    check("holiday observed july4 2026 (sat->fri)", dt.date(2026, 7, 3) in tk.federal_holidays(2026))
    check("business day add over weekend", tk.add_business_days(dt.date(2026, 11, 6), 2) == dt.date(2026, 11, 10))
    check("business day add over holiday", tk.add_business_days(dt.date(2026, 11, 24), 3) == dt.date(2026, 11, 30))
    check("num parens", tk.num("(1,234.5)") == -1234.5 and tk.num("--") is None)
    # insider helpers
    check("adoption date parsed", bl.adoption_date("The sales were made under a Rule 10b5-1 trading plan adopted on March 3, 2025.") == dt.date(2025, 3, 3))
    check("adoption none without plan words", bl.adoption_date("Shares were granted on March 3, 2025.") is None)
    check("add_months clip", bl.add_months(dt.date(2025, 8, 31), 6) == dt.date(2026, 2, 28))
    check("person match initials", bl.same_person(bl.person_tokens("Lian Brian"), bl.person_tokens("BRIAN LIAN")))
    check("person no match", not bl.same_person(bl.person_tokens("Lian Brian"), bl.person_tokens("Rouan Sarah Kathryn")))
    # section finder: table of contents + split headings
    lines = ["# SOURCE: x", "# FORM: 10-K | FILED: 2026-01-01 | PERIOD: 2025-12-31 | ACCESSION: a | ROLE: annual | ITEMS: ", "", "PA", "RT I", "Item 1. | Business | 1", "Item 1A. | Risk Factors | 5",
             "PA", "RT I", "Item 1. Busi", "ness.", "text " * 3, "more", "more", "Item 1A. Ris", "k Factors.", "risk", "risk", "risk"]
    secs = bd.find_sections(lines)
    ids = [(s["id"], s["start"]) for s in secs]
    check("sections ignore TOC", ("1", 10) in ids and ("1A", 15) in ids and ("1", 6) not in ids, str(ids))
    check("split heading title joined", any(s["title"].startswith("Business") for s in secs), str([s["title"] for s in secs]))
    # synthetic folder end to end
    tk.RESEARCH.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="ZZTOOLS_", dir=tk.RESEARCH))
    temporary = []
    try:
        (root / "text").mkdir(parents=True)
        (root / "derived").mkdir()
        (root / "agents" / "stock-filings-reader").mkdir(parents=True)
        (root / "identity.json").write_text(json.dumps({"ticker": "ZZ", "name": "Test Co", "mode": "live", "filer_type": "domestic"}))
        text = "\n".join(lines + ["We have substantial doubt about our ability; going concern.", "We entered into an at-the-market sales agreement.", "Item 7. MD&A", "x", "y", "z", "w"])
        (root / "text" / "2026-01-01_10-K_000000000000000001_zz.txt").write_text(text)
        (root / "filings_index.csv").write_text("filingDate,reportDate,form,items,accessionNumber,primaryDocument,primaryDocDescription,acceptanceDateTime,isInlineXBRL\n2026-01-01,2025-12-31,10-K,,0000000000-00-000001,a.htm,,2026-01-01T12:00:00.000Z,1\n")
        r = run("build_digest.py", str(root))
        check("digest runs", r.returncode == 0, r.stderr[-200:])
        hits = (root / "digest" / "hits.csv").read_text()
        check("digest hits topics", "going_concern" in hits and "atm_equity_line" in hits)
        r = run("read_section.py", str(root), "2026-01-01_10-K_000000000000000001_zz.txt", "--grep", "going concern")
        check("read_section grep", "going concern" in r.stdout, r.stderr[-200:])
        r = run("read_section.py", str(root), "../identity.json", "--lines", "1-2")
        check("read_section refuses path escape", r.returncode != 0)
        r = run("read_section.py", str(root), "2026-01-01_10-K_000000000000000001_zz.txt", "--lines", "1-400", "--max-lines", "5")
        check("read_section caps output", "truncated" in r.stdout)
        # insider ledger with a late Form 4, a P/S pair and a 144 notice
        hdr = "accession,filed,form,period_of_report,issuer_cik,issuer,symbol,owner,owner_cik,owner_ciks,relationship,officer_title,rule_10b5_1,source_url,table,security,date,code,shares,price,acq_disp,shares_after,direct_indirect,nature,footnotes,exercise_price,exercisable,expires,underlying,underlying_shares\n"
        rows = ["a1,2026-03-20,4,,1,ZZ,ZZ,Doe Jane,111,111,director,,false,u,non_derivative_transaction,Common,2026-03-10,P,100,10,A,100,D,,,,,,,\n",
                "a2,2026-05-05,4,,1,ZZ,ZZ,Doe Jane,111,111,director,,true,u,non_derivative_transaction,Common,2026-05-04,S,100,12,D,0,D,,Sold under a Rule 10b5-1 trading plan adopted on April 20 2026.,,,,,\n"]
        (root / "derived" / "insider_filings.csv").write_text(hdr + "".join(rows))
        (root / "derived" / "form144_notices.csv").write_text("accession,filed,form,issuer,issuer_cik,person,relationship,class_title,units_to_sell,aggregate_market_value,units_outstanding,approx_sale_date,exchange,acquired_date,acquisition_nature,plan_adoption_date,notice_date,remarks,past_3m_sales,source_url\nn1,2026-05-04,144,ZZ,1,JANE DOE,director,Common,100,1200,1000,05/04/2026,N,,,2026-04-20,,,,u\n")
        r = run("build_insider_ledger.py", str(root))
        check("ledger runs", r.returncode == 0, r.stderr[-300:])
        flags = (root / "digest" / "insider_flags.csv").read_text()
        check("S16-A late candidate", "S16-A" in flags)
        check("S16-B pair", "S16-B" in flags)
        check("R10B5-A cooling-off candidate", "R10B5-A" in flags and "review candidate" in flags, flags[-300:])
        check("144 matched", "same-person Form 4 sale" in (root / "digest" / "form144_match.csv").read_text())
        # claims verifier and handoff
        good = {"claim_id": "FIL-001", "agent": "stock-filings-reader", "label": "FACT", "statement": "Shares outstanding were 123,456,789.", "source": "text/2026-01-01_10-K_000000000000000001_zz.txt", "location": "lines 1-3", "published": "2026-01-01", "origin": "10-K", "confidence": "high"}
        badc = {**good, "claim_id": "FIL-002", "label": "MAYBE", "source": "text/missing.txt"}
        calc = {**good, "claim_id": "FIL-003", "label": "CALC", "depends_on": ["FIL-999"]}
        (root / "agents" / "stock-filings-reader" / "claims.jsonl").write_text("\n".join(json.dumps(x) for x in (good, badc, calc)) + "\n")
        r = run("verify_claims.py", str(root))
        out = (root / "tables" / "claims_check.csv").read_text()
        check("verify_claims exits 1 on errors", r.returncode == 1)
        check("verify_claims finds bad label, missing source, unknown dependency, absent number", "label" in out and "source_exists" in out and "depends_on" in out and "numbers_in_source" in out, out)
        r = run("handoff.py", "check", str(root), "--agent", "stock-filings-reader")
        check("handoff check blocks without findings", r.returncode == 1 and "BLOCKED" in r.stdout)
        r = run("handoff.py", "save", str(root), "--agent", "stock-filings-reader", inp="# stock-filings-reader findings: ZZ as of 2026-11-09 21:49\nbody\n")
        check("handoff save", r.returncode == 0, r.stderr[-200:])
        r = run("handoff.py", "save", str(root), "--agent", "stock-filings-reader", inp="not a findings file")
        check("handoff save rejects wrong header", r.returncode != 0)
        (root / "agents" / "stock-filings-reader" / "search_log.md").write_text("log\n")
        (root / "agents" / "stock-filings-reader" / "claims.jsonl").write_text(json.dumps(good) + "\n")  # the earlier fixture holds deliberately bad claims
        r = run("handoff.py", "check", str(root), "--agent", "stock-filings-reader", "--as-of", "2026-11-09 21:49")
        check("handoff check ok", r.returncode == 0, r.stdout)
        r = run("handoff.py", "check", str(root), "--agent", "stock-filings-reader", "--as-of", "2026-11-09 21:4")
        check("handoff check exact as-of", r.returncode == 1)
        malformed = {**good, "claim_id": "FIL-004", "confidence": ["high"]}
        (root / "agents" / "stock-filings-reader" / "claims.jsonl").write_text(json.dumps(malformed) + "\n")
        check("handoff rejects non-string confidence", run("handoff.py", "check", str(root), "--agent", "stock-filings-reader").returncode == 1)
        r = run("verify_claims.py", str(root), "--agent", "stock-filings-reader")
        check("verify_claims rejects non-string confidence", r.returncode == 1 and "confidence" in (root / "tables" / "claims_check.csv").read_text())
        # Claim paths must stay in the selected cache, including when --agent is used.
        escaped = {**good, "claim_id": "FIL-004", "source": "../OTHER/secret.txt"}
        (root / "agents" / "stock-filings-reader" / "claims.jsonl").write_text(json.dumps(escaped) + "\n")
        r = run("verify_claims.py", str(root), "--agent", "stock-filings-reader")
        check("verify_claims rejects sibling source", r.returncode == 1 and "outside folder" in (root / "tables" / "claims_check.csv").read_text())
        peer = Path(tempfile.mkdtemp(prefix="ZZPEER_", dir=tk.RESEARCH))
        temporary.append(peer)
        (peer / "text").mkdir()
        (peer / "text" / "peer.txt").write_text("Shares outstanding were 123,456,789.\n")
        (peer / "identity.json").write_text(json.dumps({"ticker": "ZZPEER", "mode": "live"}))
        cited = {**good, "claim_id": "FIL-004", "source": f"../{peer.name}/text/peer.txt", "location": "line 1"}
        (root / "agents" / "stock-filings-reader" / "claims.jsonl").write_text(json.dumps(cited) + "\n")
        r = run("verify_claims.py", str(root), "--agent", "stock-filings-reader")
        check("verify_claims allows same-mode peer cache", r.returncode == 0, r.stdout[-200:])
        (peer / "identity.json").write_text(json.dumps({"ticker": "ZZPEER", "mode": "as_of", "as_of_utc": "2026-11-09T21:49:00Z"}))
        r = run("verify_claims.py", str(root), "--agent", "stock-filings-reader")
        check("verify_claims rejects as-of/live peer mixing", r.returncode == 1 and "incompatible peer" in (root / "tables" / "claims_check.csv").read_text())
        (root / "identity.json").write_text(json.dumps({"ticker": "ZZ", "mode": "as_of", "as_of_utc": "2026-11-09T21:49:00Z"}))
        check("verify_claims allows matching as-of peer", run("verify_claims.py", str(root), "--agent", "stock-filings-reader").returncode == 0)
        (peer / "identity.json").write_text(json.dumps({"ticker": "ZZPEER", "mode": "as_of", "as_of_utc": "2026-11-09T21:50:00Z"}))
        check("verify_claims rejects different as-of cutoffs", run("verify_claims.py", str(root), "--agent", "stock-filings-reader").returncode == 1)
        (root / "identity.json").write_text(json.dumps({"ticker": "ZZ", "mode": "live"}))
        (root / "text" / "2026-01-01_10-K_000000000000000001_zz.txt").write_text(text + "\n")
        beyond = {**good, "claim_id": "FIL-004", "location": f"line {len(text.split(chr(10))) + 1}"}
        (root / "agents" / "stock-filings-reader" / "claims.jsonl").write_text(json.dumps(beyond) + "\n")
        r = run("verify_claims.py", str(root), "--agent", "stock-filings-reader")
        check("verify_claims rejects line after trailing newline", r.returncode == 1 and "location_range" in (root / "tables" / "claims_check.csv").read_text())
        beyond["location"] += "; see Form 10-K"
        (root / "agents" / "stock-filings-reader" / "claims.jsonl").write_text(json.dumps(beyond) + "\n")
        check("verify_claims rejects out-of-range line despite other source text", run("verify_claims.py", str(root), "--agent", "stock-filings-reader").returncode == 1)
        bad_date = {**good, "published": "20261109"}
        (root / "agents" / "stock-filings-reader" / "claims.jsonl").write_text(json.dumps(bad_date) + "\n")
        check("verify_claims requires dashed ISO date", run("verify_claims.py", str(root), "--agent", "stock-filings-reader").returncode == 1)
        check("handoff requires dashed ISO date", run("handoff.py", "check", str(root), "--agent", "stock-filings-reader").returncode == 1)
        (root / "agents" / "stock-filings-reader" / "claims.jsonl").write_text(json.dumps(good) + "\n" + json.dumps(good) + "\n")
        check("handoff rejects duplicate claim IDs", run("handoff.py", "check", str(root), "--agent", "stock-filings-reader").returncode == 1)
        (root / "agents" / "stock-filings-reader" / "claims.jsonl").write_text("\n".join(json.dumps(x) for x in (good, badc, calc)) + "\n")
        r = run("handoff.py", "appendix", str(root))
        check("appendix", r.returncode == 0 and (root / "report_appendix.md").is_file())
        other = root / "agents" / "stock-other"
        other.mkdir()
        (other / "claims.jsonl").symlink_to(root / "agents" / "stock-filings-reader" / "claims.jsonl")
        check("appendix rejects symlink claims", run("handoff.py", "appendix", str(root)).returncode != 0)
        (other / "claims.jsonl").unlink()
        other.rmdir()
        # Empty Reg SHO ratios and expired options must not corrupt positioning output.
        (root / "raw" / "finviz").mkdir(parents=True)
        (root / "raw" / "finviz" / "price_history_daily.csv").write_text("Date,Close,High,Low,Volume\n11/09/2026,10,11,9,100\n11/09/2026,10,11,9,100\n")
        (root / "raw" / "finviz" / "options_chain.csv").write_text("Expiry,Type,Strike,Open Int.,Volume,IV\n11/06/2026,call,10,1,1,0.5\n11/20/2026,call,10,2,2,0.5\n11/27/2026,put,10,3,2,0.5\n")
        (root / "derived" / "finra_regsho_daily.csv").write_text("ShortVolume,TotalVolume\n,100\n")
        (root / "derived" / "ownership_13dg.csv").write_text("filed,accession,reporting_person,class_title,percent_of_class,form,event_date\n2026-11-01,a,Holder,Common,7.7,13G,2026-10-01\n2026-11-01,a,Holder,Common,,13G,2026-10-01\n")
        r = run("positioning_summary.py", str(root))
        pos = (root / "tables" / "positioning.csv").read_text() if r.returncode == 0 else ""
        check("positioning runs with empty short volume", r.returncode == 0, r.stderr[-200:])
        check("positioning excludes expired options", "options_2026-11-06" not in pos and "options_2026-11-20" in pos)
        check("positioning zero-call OI unknown", "unknown (zero call OI)" in pos)
        check("positioning keeps populated holder row", "7.7%" in pos)
        (root / "derived" / "ownership_13dg.csv").write_text("filed,accession,reporting_person,class_title,percent_of_class,form,event_date\n2026-11-01,a,Holder,Common,7.7,13G,2026-10-01\n2026-11-02,b,Holder,Common,,13G/A,2026-11-02\n")
        (root / "derived" / "finra_regsho_daily.csv").write_text("Date,Symbol,Market,ShortVolume,TotalVolume\n20261109,ZZ,B,10,100\n20261109,ZZ,Q,90,100\n20261108,ZZ,B,10,100\n")
        r = run("positioning_summary.py", str(root))
        pos = (root / "tables" / "positioning.csv").read_text() if r.returncode == 0 else ""
        check("positioning does not carry holder percentage into later blank filing", r.returncode == 0 and "13dg_Holder" not in pos and "13dg_latest_pct_unknown_count" in pos)
        check("positioning aggregates markets before daily Reg SHO mean", "30.0%" in pos)
        (root / "raw" / "finviz" / "price_history_daily.csv").write_text("Date,Close,High,Low,Volume\n11/08/2026,8,9,7,100\n11/09/2026,10,11,9,100\n11/09/2026,11,12,10,100\n")
        r = run("positioning_summary.py", str(root))
        pos = (root / "tables" / "positioning.csv").read_text() if r.returncode == 0 else ""
        check("positioning excludes conflicting price date with warning", r.returncode == 0 and "last_close,8" in pos and "conflicting daily price" in r.stderr)
        (root / "raw" / "finviz" / "short_interest_history.csv").write_text("Settlement Date,Short Interest,Short Float,Short Ratio\n2026-11-09,100,10,2\n2026-11-09,200,20,4\n2026-10-31,50,5,1\n")
        r = run("positioning_summary.py", str(root))
        pos = (root / "tables" / "positioning.csv").read_text() if r.returncode == 0 else ""
        check("positioning excludes conflicting short-interest date", r.returncode == 0 and "short_interest_latest,50" in pos and "conflicting short-interest" in r.stderr)
        (root / "derived" / "finra_regsho_daily.csv").write_text("Date,Symbol,Market,ShortVolume,TotalVolume\n20261109,ZZ,B,10,100\n20261109,ZZ,B,90,100\n20261108,ZZ,Q,20,100\n")
        r = run("positioning_summary.py", str(root))
        pos = (root / "tables" / "positioning.csv").read_text() if r.returncode == 0 else ""
        check("positioning excludes conflicting Reg SHO date", r.returncode == 0 and "20.0%" in pos and "conflicting Reg SHO" in r.stderr)
        (root / "raw" / "finviz" / "options_chain.csv").write_text("Contract Name,Expiry,Type,Strike,Open Int.,Volume,IV\nA,11/20/2026,call,10,2,2,0.5\nA,11/20/2026,call,10,7,2,0.5\nB,11/20/2026,put,10,3,2,0.5\n")
        r = run("positioning_summary.py", str(root))
        pos = (root / "tables" / "positioning.csv").read_text() if r.returncode == 0 else ""
        check("positioning excludes conflicting options contract", r.returncode == 0 and "call OI 0" in pos and "conflicting options contracts" in r.stderr)
        (root / "derived" / "ownership_13dg.csv").write_text("filed,accession,reporting_person,class_title,percent_of_class,form,event_date\n2026-11-01,a,Holder,Common,7.7,13G,2026-10-01\n2026-11-01,a,Holder,Common,8.8,13G,2026-10-01\n")
        r = run("positioning_summary.py", str(root))
        pos = (root / "tables" / "positioning.csv").read_text() if r.returncode == 0 else ""
        check("positioning excludes conflicting holder percentages", r.returncode == 0 and "13dg_Holder" not in pos and "13dg_latest_pct_unknown_count" in pos and "conflicting 13D/G" in r.stderr)
        run("prepare_company.py", str(root))
        prepared = json.loads((root / "tables" / "PREPARED.json").read_text())
        check("prepare surfaces positioning warnings", "WARN" in prepared["steps"]["positioning_summary.py"]["output"])
        # valuation maths
        temp = Path(tempfile.mkdtemp())
        temporary.append(temp)
        inp = temp / "in.json"
        inp.write_text(json.dumps({"cash_flows": [{"year": 1, "value": 100}], "discount_rate": 0.1, "terminal": {"multiple": 10}, "net_cash": 50, "shares": 10}))
        r = run("valuation_calc.py", "dcf", "--inputs", str(inp))
        d = json.loads(r.stdout)
        check("dcf value", abs(d["enterprise_value"] - (100 / 1.1 + 1000 / 1.1)) < 1e-6, str(d.get("enterprise_value")))
        check("dcf per share", abs(d["equity_value_per_share"] - (d["enterprise_value"] + 50) / 10) < 1e-9)
        r = run("valuation_calc.py", "reverse", "--inputs", str(inp), "--target-ev", "2200")
        check("reverse scale", abs(json.loads(r.stdout)["scale_factor"] - 2.2) < 1e-6, r.stdout[-200:])
        r = run("valuation_calc.py", "dcf", "--inputs", str(inp), "--out", str(temp / "should_fail.json"))
        check("valuation --out outside research refused", r.returncode != 0)
        bad = temp / "bad.json"
        bad.write_text(json.dumps({"cash_flows": [{"year": 1, "value": 1}], "discount_rate": 0.03, "terminal": {"growth": 0.05}}))
        check("terminal growth >= rate refused", run("valuation_calc.py", "dcf", "--inputs", str(bad)).returncode != 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        for directory in temporary:
            shutil.rmtree(directory, ignore_errors=True)
    # batch 2: catalysts, offerings, runway, rnpv, transcript, trials parsers
    import build_catalysts as bc  # noqa: E402
    import build_obligations as bo  # noqa: E402
    check("future date same year later month", bc.is_future("October 15, 2032", "2026-10-29") and bc.is_future("fourth quarter of 2026", "2026-10-29"))
    check("past date rejected", not bc.is_future("May 2023", "2026-10-29") and not bc.is_future("second quarter of 2026", "2026-10-29"))
    notes = [m for f, rx in bo.PATTERNS if f == "notes_terms" for m in [rx.search("$225.0 million aggregate principal amount of 2.00% convertible senior notes due 2032")] if m]
    check("offering notes pattern", bool(notes) and notes[0].group(3) == "2.00" and notes[0].group(4) == "2032", str(notes and notes[0].groups()))
    inp2 = Path(tempfile.mkdtemp()) / "r.json"
    inp2.write_text(json.dumps({"base_year": 2026, "revenue": [{"year": 2028, "value": 1000}], "development_costs": [{"year": 2027, "value": 100}], "operating_margin": 0.5, "tax_rate": 0.2,
                                "probability_of_success": 0.5, "discount_rate": 0.1}))
    r = run("valuation_calc.py", "rnpv", "--inputs", str(inp2))
    exp = (1000 * 0.5 * 0.8 * 0.5) / 1.1 ** 2 - 100 / 1.1
    check("rnpv value", r.returncode == 0 and abs(json.loads(r.stdout)["enterprise_value"] - exp) < 1e-9, r.stdout[-200:] + r.stderr[-200:])
    inp3 = Path(tempfile.mkdtemp()) / "cal.json"
    inp3.write_text(json.dumps({"cash_flows": [{"year": 2029, "value": 1}], "discount_rate": 0.1}))
    check("dcf rejects calendar years", run("valuation_calc.py", "dcf", "--inputs", str(inp3)).returncode != 0)
    root2 = Path(tempfile.mkdtemp(prefix="ZZTOOLS2_", dir=tk.RESEARCH))
    try:
        (root2 / "text").mkdir(parents=True)
        (root2 / "raw" / "finviz").mkdir(parents=True)
        (root2 / "identity.json").write_text(json.dumps({"ticker": "ZZ2", "name": "T2", "mode": "live"}))
        (root2 / "text" / "2026-10-01_10-Q_000000000000000002_zz.txt").write_text("# SOURCE: x\n# FORM: 10-Q | FILED: 2026-10-01 | PERIOD: 2026-09-30 | ACCESSION: 0000000000-00-000002 | ROLE: interim | ITEMS: \n\n"
                                                                                  "We expect to report topline results in the fourth quarter of 2027 from the Phase 3 trial of our lead program.\nIn May 2023, we reported topline results from the Phase 2 trial of the program.\n")
        r = run("build_catalysts.py", str(root2))
        out = (root2 / "tables" / "catalysts.csv").read_text() if r.returncode == 0 else r.stderr
        check("catalysts keeps future, drops past", "fourth quarter of 2027" in out and "May 2023" not in out, out[:300])
        (root2 / "agents" / "stock-management-analyst" / "work").mkdir(parents=True)
        t = root2 / "agents" / "stock-management-analyst" / "work" / "call.txt"
        t.write_text("Full Transcript\nOperator\nWelcome to the call.\nJane Roe\nCEO, Test Co\nWe expect revenue between $10 million and $12 million next year.\nBob Poe\nAnalyst, Big Bank\nWhat is your target margin of 40%?\nJane Roe\nCEO, Test Co\nThank you.\nBob Poe\nAnalyst, Big Bank\nOne more.\nOperator\nThat concludes the call.\n")
        r = run("parse_transcript.py", str(root2), "agents/stock-management-analyst/work/call.txt")
        dg = (root2 / "agents" / "stock-management-analyst" / "work" / "call.digest.md")
        check("transcript speakers and guidance", r.returncode == 0 and dg.is_file() and "Jane Roe" in dg.read_text() and "between $10 million" in dg.read_text(), r.stderr[-200:])
        check("transcript guidance cites sentence line", "line 6 Jane Roe" in dg.read_text(), dg.read_text()[-250:])
        inline = root2 / "agents" / "stock-management-analyst" / "work" / "inline.txt"
        inline.write_text("Jane Roe: We expect revenue of $10 million next year.\nBob Poe: What is the target of 40%?\n")
        r = run("parse_transcript.py", str(root2), "agents/stock-management-analyst/work/inline.txt")
        inline_digest = inline.with_suffix(".digest.md")
        check("transcript keeps inline speaker text", r.returncode == 0 and "line 1 Jane Roe" in inline_digest.read_text(), r.stderr[-200:])
        mixed = root2 / "agents" / "stock-management-analyst" / "work" / "mixed.txt"
        mixed.write_text("Full Transcript\nOperator\nWelcome.\nJane Roe\nCEO, Test Co\nForward-looking statements are subject to risks and uncertainties.\nOur first question is about the outlook.\nBob Poe: We expect revenue of $10 million.\nOperator: We will open the line for questions.\nAlice So: What is your target margin of 40%?\n")
        r = run("parse_transcript.py", str(root2), "agents/stock-management-analyst/work/mixed.txt")
        mixed_turns = mixed.with_suffix(".turns.csv").read_text() if r.returncode == 0 else ""
        mixed_rows = list(csv.DictReader(mixed_turns.splitlines()))
        check("transcript handles mixed headings and inline speakers", r.returncode == 0 and ",prepared,Operator," in mixed_turns and
              ",prepared,Bob Poe," in mixed_turns and ",qa,Alice So," in mixed_turns, r.stderr[-200:] + mixed_turns[-400:])
        check("transcript keeps hyphenated prose within speaker turn", r.returncode == 0 and
              not any(row["speaker"] == "Forward" for row in mixed_rows) and
              any(row["speaker"] == "Jane Roe (CEO, Test Co)" and row["first_line"] == "4" and row["last_line"] == "7" for row in mixed_rows),
              r.stderr[-200:] + mixed_turns[-400:])
        check("transcript rejects escape", run("parse_transcript.py", str(root2), "../identity.json").returncode != 0)
        (root2 / "agents" / "stock-geopolitics-analyst" / "work").mkdir(parents=True)
        cj = root2 / "agents" / "stock-geopolitics-analyst" / "work" / "ct.json"
        cj.write_text(json.dumps({"studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT1", "briefTitle": "T"}, "statusModule": {"overallStatus": "RECRUITING"}, "designModule": {"phases": ["PHASE3"], "enrollmentInfo": {"count": 10, "type": "ESTIMATED"}}}}]}))
        r = run("parse_ctgov.py", str(root2), "agents/stock-geopolitics-analyst/work/ct.json")
        check("ctgov parse", r.returncode == 0 and "NCT1" in (root2 / "agents" / "stock-geopolitics-analyst" / "work" / "ct.trials.csv").read_text(), r.stderr[-200:])
        cj.write_text(json.dumps({"studies": [{"protocolSection": None}, {"protocolSection": {"identificationModule": {"nctId": "NCT1"}}},
                                               {"protocolSection": {"identificationModule": {"nctId": "NCT1"}}}]}))
        r = run("parse_ctgov.py", str(root2), "agents/stock-geopolitics-analyst/work/ct.json")
        trial_csv = (root2 / "agents" / "stock-geopolitics-analyst" / "work" / "ct.trials.csv").read_text()
        check("ctgov excludes malformed and duplicate studies visibly", r.returncode == 0 and trial_csv.count("NCT1") == 1 and
              "WARN: excluded malformed" in r.stderr and "WARN: excluded duplicate" in r.stderr, r.stderr[-300:])
        check("ctgov rejects non-ctgov json", run("parse_ctgov.py", str(root2), "identity.json").returncode != 0)
        r = run("audit_claims.py", str(root2))
        check("audit_claims runs on a folder without claims", r.returncode == 0, r.stderr[-200:])
        import valuation_calc as vc  # noqa: E402
        calc_inputs = {"base_year": 2026, "revenue": [{"year": 2027, "value": 100}], "development_costs": [{"year": 2027, "value": 10}],
                       "operating_margin": 1, "tax_rate": 0, "probability_of_success": 0.5, "discount_rate": 0.1}
        calc_file = root2 / "agents" / "stock-management-analyst" / "work" / "calc.json"
        calc_data = vc.rnpv(calc_inputs)
        calc_data["rnpv_inputs"]["revenue"][0]["value"] = 200
        calc_file.write_text(json.dumps(calc_data))
        claims_dir = root2 / "agents" / "stock-management-analyst"
        claims_dir.joinpath("claims.jsonl").write_text(json.dumps({"claim_id": "MGT-001", "agent": "stock-management-analyst", "label": "CALC",
                                                           "statement": "rNPV result", "source": "agents/stock-management-analyst/work/calc.json",
                                                           "location": "enterprise_value", "published": "2026-10-01", "origin": "calculation", "confidence": "high"}) + "\n")
        r = run("audit_claims.py", str(root2))
        audit = (root2 / "tables" / "claim_audit.md").read_text()
        check("audit recomputes original rNPV inputs", r.returncode == 0 and "MISMATCH" in audit, r.stderr[-200:])
        calc_file.write_text(json.dumps(vc.rnpv({**calc_inputs, "terminal": {"multiple": 10}})))
        r = run("audit_claims.py", str(root2))
        audit = (root2 / "tables" / "claim_audit.md").read_text() if r.returncode == 0 else ""
        check("audit accepts valid rNPV terminal value", r.returncode == 0 and "1 files matched, 0 mismatched" in audit and "MISMATCH" not in audit, r.stderr[-200:] + audit[-300:])
        unsafe = Path(tempfile.mkdtemp(prefix="ZZUNSAFE_", dir=tk.RESEARCH))
        try:
            (unsafe / "identity.json").write_text(json.dumps({"ticker": "ZZUNSAFE", "mode": "live"}))
            (unsafe / "tables").symlink_to(root2 / "tables", target_is_directory=True)
            check("audit refuses symlinked tables", run("audit_claims.py", str(unsafe)).returncode != 0)
        finally:
            shutil.rmtree(unsafe, ignore_errors=True)
    finally:
        shutil.rmtree(root2, ignore_errors=True)
    root3 = tk.RESEARCH / "ZZTOOLS3"
    shutil.rmtree(root3, ignore_errors=True)
    try:
        (root3 / "agents" / "stock-filings-reader").mkdir(parents=True)
        (root3 / "identity.json").write_text(json.dumps({"ticker": "ZZ3", "mode": "live"}))
        (root3 / "agents" / "stock-filings-reader" / "claims.jsonl").write_text(json.dumps({"claim_id": "FIL-001", "statement": "Cash was 959,813 thousand USD."}) + "\n")
        (root3 / "brief.md").write_text("Cash was 959813 thousand USD [FIL-001].\nThe company raised 575 million USD.\nThe company has been growing very fast and utilizes cash in an approximately large way for a number of reasons that nobody can say clearly today.\nThe plan costs 100 USD [FIL-999].\n")
        r = run("ste_lint.py", str(root3))
        out = (root3 / "tables" / "ste_lint.md").read_text()
        check("ste_lint flags missing id, unknown id, long sentence, bad words, exit 1", r.returncode == 1 and "missing claim ID" in out and "unknown claim ID" in out and "sentence length" in out and "approximately" in out, out[:400])
        (root3 / "brief.md").write_text("Cash was 959813 thousand USD [FIL-001].\n")
        check("ste_lint passes a clean brief", run("ste_lint.py", str(root3)).returncode == 0)
        check("ste_lint rejects path escape", run("ste_lint.py", str(root3), "--file", "../identity.json").returncode != 0)
    finally:
        shutil.rmtree(root3, ignore_errors=True)
    print(f"{N - len(FAILS)}/{N} checks passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
