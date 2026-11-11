---
name: analysis-scripts
description: Offline scripts that pre-compute what agents used to rebuild each run (filing digest, insider ledger, financial and obligation tables, catalysts, runway, rNPV/DCF, positioning, peers, benchmark, transcripts, trials, claim checks, handoffs). Use before reading raw filings or writing your own script.
---

# Analysis scripts (all offline, stdlib only)
Run with `ROOT/.venv/bin/python -I ROOT/scripts/<script>.py <folder> ...` (`<folder>` = ticker or `RESEARCH_DIR` name). They read only that research folder, never fetch, and respect an as-of cut. Outputs are screening aids: cite the original passage or row, and treat hits, flags and metrics as review candidates.

| Script | Produces (under the folder) | Notes |
|---|---|---|
| `prepare_company.py` | runs the seven builders below | orchestrator, phase 1b; exit 0 only if all steps ran |
| `build_digest.py` | `digest/digest.md`, `sections.csv`, `hits.csv` | section index and keyword hits; open text with `read_section.py` |
| `read_section.py <folder> <file> --item 7 \| --lines A-B \| --grep RX` | bounded numbered lines | never print whole filings |
| `build_insider_ledger.py` | `digest/insider_ledger.csv`, `insider_flags.csv`, `form144_match.csv`, `insider_summary.md` | S16-A/B, R10B5-A, F144-A review candidates, UNKNOWN where inputs are missing |
| `build_tables.py [--history-years 5]` | `tables/financial_summary.md`, `statements_long.csv`, `xbrl_quarterly.csv`, `reconciliation.csv` | Finviz vs XBRL, TTM, runway arithmetic |
| `build_obligations.py` | `tables/obligations_xbrl.md/.csv`, `offerings.csv` | debt, leases, purchase commitments, dilutive securities, share counts, raises; offering terms by pattern with line numbers |
| `build_catalysts.py` | `tables/catalysts.md/.csv` | forward-dated sentences (trials, financing, disputes, supply) |
| `proxy_tables.py` | `tables/proxy_tables.md/.csv` | raw summary-compensation, ownership, equity-award rows |
| `positioning_summary.py` | `tables/positioning.md/.csv` | price, volatility, short interest, Reg SHO, earnings reactions, options snapshot, 13D/G |
| `peer_table.py <target> <peers...>` | target `tables/peers.md/.csv` | same cutoff required; do not mix currencies |
| `benchmark_compare.py <target> <bench>` | `tables/benchmark_<bench>.md/.csv` | fetch the benchmark first: `fetch_company.py XBI --instrument` |
| `runway_scenarios.py [--burn-growth ...] [--raise Q:AMT:PRICE]` | `tables/runway_scenarios.md/.csv` | arithmetic only; you label the assumptions |
| `valuation_calc.py bridge\|dcf\|rnpv\|reverse\|grid` | JSON; save with `--out research/<folder>/tables/<name>.json` (only that location is accepted) | you supply assumptions in an inputs JSON; cite saved inputs and outputs in CALC claims |
| `parse_transcript.py <folder> <rel path .txt>` | `<name>.digest.md`, `.turns.csv` | speakers, prepared vs Q&A, guidance sentences; save page text first |
| `parse_ctgov.py <folder> <rel path .json>` | `<name>.trials.csv` | ClinicalTrials.gov API v2 JSON saved by `agent_fetch.py public` |
| `verify_claims.py` | `tables/claims_check.csv` | schema, citations, numbers in cited lines; exit 1 on ERROR |
| `audit_claims.py` | `tables/claim_priority.csv`, `claim_audit.md` | priority, cycles, single-origin inferences, recompute of valuation_calc outputs |
| `coverage_check.py` | `tables/coverage_check.csv/.md` | required filings, events and keywords that no claim cites; exit 1 if any |
| `cost_ledger.py report <stream.jsonl>` | per-agent turns, tokens, wall time | `stamp` filter adds arrival times; launcher `run_deep_dive.sh` does both |
| `handoff.py check\|save\|appendix` | agent `findings.md`, `report_appendix.md` | orchestrator bookkeeping |

## Scripts-first rule
If you need something that is arithmetic, parsing or table-building, look here first. If you write a reusable script in `work/`, add a line to `work/PROMOTE.md` (script name, what it does, inputs, outputs, why the shared scripts did not cover it). The orchestrator collects these so the script can be reviewed and promoted; a promoted script gets a row in this table.
