---
name: company-data-fetch
description: Fetch and cache all primary data for one listed company (SEC filings, insiders and holders, Finviz statements/price/options, FINRA short data) with one command, then read the inventory. Use at the start of any company analysis, and for each peer.
---

# Company data fetch (run this first)

```bash
cd ~/Workspace/personal/trading/fundamental-analyser
.venv/bin/python -I scripts/fetch_company.py <TICKER>          # first run 1.5-3.5 min; cached re-run about 1 s
```
Peers: run it again per peer ticker (sequentially: SEC and Finviz rate limits are shared). Historical research: add `--as-of "YYYY-MM-DD HH:MM"` (New York time; a time is required). The script builds `research/<TICKER>_asof_<stamp>/` limited to what was knowable then and prints `RESEARCH_DIR=<folder>`; use that folder everywhere, run peers with the same flag, and do not apply cutoffs yourself (`INVENTORY.md` starts with `AS-OF MODE`). Options: `--only sec,insiders,finviz,finra,macro,derived`, `--refresh`, `--cik N` (when the ticker is not found, e.g. odd share classes). If `.venv` is missing: `uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r scripts/requirements.txt`. Full usage: `scripts/README.md`.

## Read in this order (do not re-fetch what is already there)
1. `research/<TICKER>/INVENTORY.md`: identity, what exists, what failed, caps and gaps, CURRENCY MISMATCH warnings.
2. `identity.json` (CIK, filer type, fiscal year end, Finviz profile, currencies) and `filings_index.csv` (every SEC filing with form, items, acceptance time).
3. `text/` holds filings as plain text, named `<filed>_<form>_<accession>_<doc>.txt`; header lines start with `#` and give the SOURCE URL, form, filing date, period. The original in `raw/sec/filings/` is authoritative. 8-K item codes are in the header (2.02 results, 5.02 officer change, 4.01 auditor change, 4.02 restatement).
4. `raw/finviz/` statements (annual and quarterly income, balance sheet, cash flow), daily prices, options chain snapshot, short-interest history, insiders, news, 90-column stats row. `manifest.json` lists every file with source URL, retrieval time and status.
5. `derived/`: `insider_filings.csv`, `form144_notices.csv`, `ownership_13dg.csv` (target is the issuer), `earnings_events.csv`, `finra_short_interest_latest.csv`, `finra_regsho_daily.csv`.

## Rules
- Files named `*_other_issuers.csv` or `*_target_as_filer.csv` are the company's own positions in other issuers, not holders or insiders of the company.
- If `finviz_statement_currency` differs from `xbrl_reporting_currency` (foreign issuers such as TSM), Finviz has converted the figures: do not reconcile them line by line to the filings.
- Every number used in a conclusion must be checked against the filing text or XBRL, not only the Finviz CSV (see `finviz-elite-export` caveats).
- Caps are listed in INVENTORY.md (8-K 60, 6-K 12, Form 4 target filings 400, Form 144 100, 13D/G 60). If something older is needed, say so and fetch it deliberately; do not assume absence.
- Not collected here: call transcripts and audio, IR pages, presentations, 13F holders of the stock, analyst ratings table, industry/geopolitical sources, peers (run the script per peer), borrow fees, bond trades. Research agents must discover and test those and log them as untested until verified.
- Legacy `SC 13D/G` filings are listed in the index but not parsed.
- Never print or store the Finviz token; the script already keeps it out of every file.
