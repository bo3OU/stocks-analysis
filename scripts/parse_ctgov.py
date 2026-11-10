"""Normalize a ClinicalTrials.gov API v2 JSON response (already saved in a research folder) into a trial table.

The agent fetches with `agent_fetch.py public` (e.g. https://clinicaltrials.gov/api/v2/studies?query.spons=<sponsor>&pageSize=100) and
saves the JSON under its work/downloads/. This script only parses.
Output: CSV (default: next to the input, <name>.trials.csv) with NCT id, phase, status, enrollment, key dates, sponsor, conditions,
interventions, primary outcome measure and title; plus a printed count and the paging token if more pages exist.
Usage: .venv/bin/python -I scripts/parse_ctgov.py <TICKER or RESEARCH_DIR> <relative path to .json> [--out relative.csv]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_HERE = HERE if (HERE / "toolkit.py").is_file() else HERE.parents[2] / "scripts"
sys.path.insert(0, str(SOURCE_HERE))
from toolkit import clean_cell, fail, research_dir, safe_child, write_csv  # noqa: E402

FIELDS = ["nct_id", "phases", "status", "enrollment", "enrollment_type", "start", "primary_completion", "primary_completion_type", "completion", "completion_type",
          "first_posted", "last_update", "results_first_posted", "has_results", "sponsor", "conditions", "interventions", "primary_outcome", "title"]


def d(x, *keys):
    for k in keys:
        x = x.get(k, {}) if isinstance(x, dict) else {}
    return x


def text_value(x):
    return x if isinstance(x, str) else "" if x is None else str(x)


def strings(x):
    if x is None:
        return []
    if not isinstance(x, list) or any(not isinstance(v, str) for v in x):
        raise ValueError("expected a list of strings")
    return x


def extract(s):
    pr = d(s, "protocolSection")
    st, dm = d(pr, "statusModule"), d(pr, "designModule")
    if not isinstance(pr, dict) or not isinstance(st, dict) or not isinstance(dm, dict):
        raise ValueError("missing protocol/status/design object")
    nct = d(pr, "identificationModule").get("nctId", "")
    if not isinstance(nct, str) or not nct:
        raise ValueError("missing NCT ID")
    interventions = d(pr, "armsInterventionsModule").get("interventions", []) or []
    outcomes = d(pr, "outcomesModule").get("primaryOutcomes", []) or []
    if not isinstance(interventions, list) or not isinstance(outcomes, list):
        raise ValueError("interventions/outcomes must be lists")
    return {
        "nct_id": nct, "phases": ",".join(strings(dm.get("phases", []))), "status": text_value(st.get("overallStatus")),
        "enrollment": d(dm, "enrollmentInfo").get("count", ""), "enrollment_type": text_value(d(dm, "enrollmentInfo").get("type")),
        "start": text_value(d(st, "startDateStruct").get("date")),
        "primary_completion": text_value(d(st, "primaryCompletionDateStruct").get("date")),
        "primary_completion_type": text_value(d(st, "primaryCompletionDateStruct").get("type")),
        "completion": text_value(d(st, "completionDateStruct").get("date")),
        "completion_type": text_value(d(st, "completionDateStruct").get("type")),
        "first_posted": text_value(d(st, "studyFirstPostDateStruct").get("date")),
        "last_update": text_value(d(st, "lastUpdatePostDateStruct").get("date")),
        "results_first_posted": text_value(d(st, "resultsFirstPostDateStruct").get("date")),
        "has_results": s.get("hasResults", ""),
        "sponsor": text_value(d(pr, "sponsorCollaboratorsModule", "leadSponsor").get("name")),
        "conditions": clean_cell("; ".join(strings(d(pr, "conditionsModule").get("conditions", []))), 200),
        "interventions": clean_cell("; ".join(text_value(i.get("name")) for i in interventions if isinstance(i, dict)), 200),
        "primary_outcome": clean_cell(text_value(outcomes[0].get("measure")) if outcomes and isinstance(outcomes[0], dict) else "", 200),
        "title": clean_cell(text_value(d(pr, "identificationModule").get("briefTitle")), 160),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("path")
    ap.add_argument("--out")
    a = ap.parse_args()
    rd = research_dir(a.folder)
    p = safe_child(rd, a.path)
    if p is None or not p.is_file() or p.is_symlink():
        fail("input must be an existing JSON file inside the research folder")
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"),
                          parse_constant=lambda x: fail(f"nonfinite JSON number: {x}"))
    except ValueError as e:
        fail(f"not valid JSON: {e}")
    studies = data.get("studies") if isinstance(data, dict) else None
    if not isinstance(studies, list):
        fail("no 'studies' list: is this a ClinicalTrials.gov API v2 response?")
    rows_by_id, conflicted, excluded = {}, set(), 0
    for i, s in enumerate(studies, 1):
        try:
            row = extract(s)
        except (AttributeError, TypeError, ValueError) as exc:
            print(f"WARN: excluded malformed study {i}: {exc}", file=sys.stderr)
            excluded += 1
            continue
        nct = row["nct_id"]
        if nct in conflicted:
            excluded += 1
            continue
        if nct in rows_by_id:
            if rows_by_id[nct] != row:
                conflicted.add(nct)
                excluded += 1  # the earlier row is excluded as well
                print(f"WARN: excluded conflicting duplicate studies for {nct}", file=sys.stderr)
            else:
                print(f"WARN: excluded duplicate study {i}: {nct}", file=sys.stderr)
            excluded += 1
            continue
        rows_by_id[nct] = row
    rows = [row for nct, row in rows_by_id.items() if nct not in conflicted]
    outp = safe_child(rd, a.out) if a.out else p.with_suffix(".trials.csv")
    if outp is None or outp.suffix.lower() != ".csv":
        fail("--out must be a .csv path inside the research folder")
    write_csv(outp, FIELDS, rows)
    print({"studies": len(rows), "excluded": excluded, "total_count": data.get("totalCount"), "next_page_token": data.get("nextPageToken"), "out": str(outp.relative_to(rd))})


if __name__ == "__main__":
    main()
