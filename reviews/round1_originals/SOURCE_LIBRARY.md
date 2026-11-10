# Source library (what has been tested; agents use these first)

Status: **tested** = a real call worked and a figure was cross-checked (date shown). **partial** = works with limits. **blocked** = reachable only with an account or blocks automation. **untested** = identified but never called. Details and quirks are in `ROOT/skills/<name>/SKILL.md`. A source an agent finds at run time starts as untested.

| Source | Gives | Status (date) | Skill / note |
|---|---|---|---|
| SEC EDGAR via cache and `agent_fetch.py sec` | filings, exhibits, XBRL facts, Forms 3/4/5/144, 13D/G | tested (2026-11-05..08, 7 companies) | `sec-edgar-access`, `sec-insiders-and-holders` |
| SEC full-text search `efts.sec.gov/LATEST/search-index` | phrase search across filings and exhibits | tested on SNDK (2026-11-05) | `sec-edgar-access` |
| Finviz Elite exports via cache and `agent_fetch.py finviz` | statements, prices, options snapshot, short-interest history, insiders, news, earnings calendar, screener, groups, futures/forex/crypto, funds, managers (13F) | tested (2026-11-06) except Portfolio | `finviz-elite-export`, `ROOT/finviz-api-map.md` |
| FINRA short interest and Reg SHO daily files | short interest (bi-monthly), daily short-sale volume | tested (2026-11-05..08) | `finra-short-interest` |
| US Treasury par yield curve CSV | risk-free rates | tested (2026-11-05) | `other-public-data-sources` |
| FRED `fredgraph.csv?id=<SERIES>` | macro series (no key) | partial: DGS10 tested, terms not reviewed | `other-public-data-sources` |
| Earnings-call transcripts: stockanalysis.com (provider Quartr) | transcripts per ticker | partial: SNDK only; other tickers untested | `earnings-call-transcripts-and-audio` |
| Company IR sites and webcast players | releases, presentations, audio | mostly blocked (Cloudflare/Akamai/registration); AMD IR works | `playwright-browsing`, `earnings-call-transcripts-and-audio` |
| TrendForce public NAND/DRAM price tables | latest snapshot only, no unit printed | partial (2026-11-05) | `nand-price-sources` |
| DRAMeXchange prices | memory prices | blocked (member login) | `nand-price-sources` |
| USAspending recipient autocomplete | federal awards (recipient name search) | partial: autocomplete tested, award endpoints untested | `other-public-data-sources` |
| ClinicalTrials.gov API v2 | trials | tested (2026-11-05) | `other-public-data-sources` |
| openFDA | drug labels (not a complete regulatory record) | tested (2026-11-05) | `other-public-data-sources` |
| California EDD WARN workbook | layoff notices (rolling window) | tested (2026-11-05) | `other-public-data-sources` |
| House Clerk disclosure index | congressional financial disclosures | partial: index reachable, not parsed | `other-public-data-sources` |
| Senate efdsearch, ImportYeti | disclosures, shipments | blocked | `other-public-data-sources` |
| BIS export controls, OFAC, USTR, customs data, UN Comtrade, EIA, Census, industry bodies | geopolitical and industry series | untested | none yet |
| Foreign filers' home registries (Japan, Korea, Taiwan) | local filings | untested | none yet |
| Options history, borrow fees, TRACE bond trades | positioning and credit | no source configured | gaps |
| WebSearch / WebFetch | discovery / page summary | tested; summarizer, unreliable on absence | `research-tool-caveats` |

When you verify a new source (reachable, date and unit visible, figure cross-checked), add it to "New sources" in your `search_log.md` with the evidence; the user merges it here.
