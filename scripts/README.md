# Fetch scripts

One command pulls everything the research agents read, into `research/<TICKER>/`. Deterministic and cached: no LLM involved, re-runs are cheap.

```bash
cd ~/Workspace/personal/trading/fundamental-analyser
.venv/bin/python -I scripts/fetch_company.py SNDK            # everything
.venv/bin/python -I scripts/fetch_company.py MU --only finviz,derived
scripts/run_batch.sh MU TSM JPM                                # several tickers, sequentially
.venv/bin/python -I scripts/verify_sndk.py                     # regression check against hand-verified SNDK facts
```
Options: `--refresh` ignore cache, `--cik N` override ticker lookup, `--max-insider 400`, `--max-8k 60`, `--only sec,insiders,finviz,finra,macro,derived`.
Setup if `.venv` is missing: `uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r scripts/requirements.txt`. Secrets come from `.env` (`SEC_USER_AGENT`, `FINVIZ_AUTH_TOKEN`); the token is never written to disk.

## What an agent should read first
`research/<TICKER>/INVENTORY.md` (what exists, what failed, caps and gaps), then `manifest.json` (every file with source URL, retrieval time, status) and `identity.json`.

## What it fetches
| Source | Files |
|---|---|
| SEC EDGAR | filing index (all forms, items, acceptance times); latest 3 annual reports (10-K/20-F/40-F); latest 8 10-Qs; 8-Ks of the last 24 months (cap 60) with EX-99 exhibits, and contract exhibits for items 1.01/1.02/2.01/2.03/2.04/2.05; last 12 6-Ks (foreign issuers); 2 proxy statements; financing and registration documents; XBRL company facts; Forms 3/4/5, 144, 13D/G of the last 3 years parsed to CSV (raw XML kept) |
| Finviz Elite | daily price history, options chain (snapshot), FINRA short-interest history, 6 statements (annual/quarterly income, balance sheet, cash flow), insider list, news, a 90-column stats row |
| FINRA | latest short-interest file (settlement date in the manifest), last ~20 daily Reg SHO short-sale-volume files; ticker rows extracted to `derived/` |
| US Treasury | daily par yield curve (current year) |
| Derived | `derived/earnings_events.csv`: close-to-close move around each 8-K item 2.02 (acceptance time in New York, session, base and reaction dates) |

Filings are converted to text in `text/` (header lines start with `#` and give the source URL, form, filing date, period, accession). The raw original in `raw/sec/filings/` is authoritative.

## Rules it follows
- SEC requests carry the declared User-Agent; other hosts get the honest default. No browser spoofing. 403s and 404s are recorded and never circumvented.
- Sequential requests with minimum gaps: SEC 0.25 s, Finviz 0.6 s (limit 10 per 5 s), FINRA 0.4 s. 429 honours Retry-After. Bounded retries (3).
- Accession documents are cached forever; Finviz and index files are reused for 6 hours (`--refresh` to force).
- Gaps are written to INVENTORY.md; nothing is guessed or estimated.

## Not covered (needs discovery or an account; research agents handle these)
Call transcripts and audio, company IR pages, investor presentations, 13F holders of the stock, the analyst-ratings table, industry and geopolitical sources, peers (run the script for each peer ticker), borrow fees, bond trades, options history.

## Tested (2026-11-08) on seven inputs
First run takes 1.5 to 3.5 minutes per ticker; re-runs from cache take about 1 second. Disk per ticker 30 to 210 MB (`research/` is gitignored).

| Input | Why chosen | What happened |
|---|---|---|
| SNDK | young spin-off | 2 annual reports (only two exist), 6 10-Qs, 17 8-Ks; 19/19 hand-verified facts pass (`verify_sndk.py`) |
| MU | mature large cap, August year-end | 3 10-Ks, 8 10-Qs, 24 8-Ks, 36 earnings events, Finviz statements with 8 annual periods |
| TSM | foreign private issuer | 3 20-Fs, no 10-Qs, newest 12 of 111 6-Ks (cap), no earnings events (6-Ks carry no item codes). Finviz statements are in USD but the filings report in TWD: flagged as CURRENCY MISMATCH in INVENTORY.md. Its insiders do file Form 4s (1,229 rows) |
| JPM | bank, very high filing volume | index holds 67,704 filings in 3 years (mostly 424B2 structured notes, excluded from financing documents); Finviz statements use bank line items (net interest income, deposits); 899 insider rows about JPM; its 13D/G filings are mostly JPM as the filer on other companies |
| OKLO | pre-revenue small cap | 3 10-Ks, statements with zero revenue handled, 44 13D/G rows about the company |
| BRK-B | class-share ticker, large holder of other companies | ticker resolved; FINRA writes the symbol as `BRK/B` (handled); 240 insider rows about Berkshire vs 344 where Berkshire is the reporting owner in other companies (kept in a separate file) |
| ZZZZ | not a real ticker | fails cleanly with a message in INVENTORY.md, no crash |

## Things the agents must know about the output
- **Direction of ownership filings.** The SEC index lists filings where the company is the filer or the subject. `derived/insider_filings.csv`, `form144_notices.csv` and `ownership_13dg.csv` hold only rows where the target is the issuer. `*_other_issuers.csv` and `ownership_13dg_target_as_filer.csv` are the company's own positions elsewhere (informational).
- **Currency.** `identity.json` has `xbrl_reporting_currency` and `finviz_statement_currency`; if they differ, INVENTORY.md says so.
- **Caps** (INVENTORY.md lists each one that was hit): 8-Ks 60, 6-Ks 12, Form 3/4/5 target filings 400, Form 144 100, 13D/G target filings 60 (download cap 400).
- **Not parsed:** legacy `SC 13D/G` filings (HTML or text, before the XML format) are only listed in `filings_index.csv`.
- **Partial runs** (`--only`) apply only to live folders. As-of runs reject them and clear generated files on a full rerun.
- **Finviz covers US-listed tickers**; a ticker it does not know produces empty or unexpected files, recorded in the manifest.

## Point-in-time (as-of) runs
```bash
.venv/bin/python -I scripts/fetch_company.py SNDK --as-of "2026-10-29 16:00" --tz America/New_York      # a time without a UTC offset needs --tz
.venv/bin/python -I scripts/verify_asof.py                                          # regression checks on two SNDK cutoffs
```
The cutoff is an exact instant (a time is required). The script builds a separate folder `research/<TICKER>_asof_<UTC stamp>/` and prints `RESEARCH_DIR=<folder>`: give exactly that folder to the agents (its name is the `--ticker` value for `agent_fetch.py`). Agents do not re-cut script output; `INVENTORY.md` starts with an `AS-OF MODE` section listing what was excluded. Run each peer with the same `--as-of`.

| Data | Rule at the cutoff |
|---|---|
| SEC filings, exhibits, Forms 3/4/5/144, 13D/G | accepted (`acceptanceDateTime`) at or before the cutoff; date-only records count as accepted at 23:59:59 New York time of the filing day |
| XBRL company facts | use the accession acceptance instant when known; otherwise a date-only fact needs a filing date before the cutoff's New York date. Retrieval-time frames and descriptions are removed; the unfiltered file stays outside the folder |
| Daily prices (Finviz) | rows whose close (16:00 New York + 5 minutes) is at or before the cutoff; the history is split-adjusted as of retrieval, so later splits are already applied |
| Short interest | settlement dates at least 14 days before the cutoff (`--si-lag-days`; assumed publication lag, not verified); Reg SHO daily files for trade dates before the cutoff date |
| Treasury yield curve | rows assumed available by 18:00 New York time (`raw/macro/treasury_yield_curve.csv`) |
| Finviz statements, options, news, insider list, stats row, consensus | not written: live snapshots that cannot be reconstructed (recorded as `skipped_asof` in the manifest) |
| Identity fields | current SEC profile fields are omitted; verify historical identity in eligible filings |

`agent_fetch.py` enforces the same cutoff inside an as-of folder: SEC documents only for filings in that folder's `filings_index.csv`; no live SEC listings (submissions, company facts, full-text search); Finviz only for daily price history and short-interest history, cut at the cutoff.
