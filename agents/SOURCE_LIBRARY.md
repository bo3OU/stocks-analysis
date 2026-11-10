# Source library (what has been tested; agents use these first)

Status is a dated access observation, not a license or present availability: **tested** = the source was opened and a relevant claim or figure, date, scope and unit where relevant checked; **partial** = limited test; **blocked** = access failed; **untested** = not checked. Read relevant `ROOT/skills/<name>/SKILL.md` if present. Check the source's current terms, dates, scope and units for the actual claim; never count mirrors as independent origins. Missing skills or tools are a coverage limit, not permission to invent access.

| Source | Gives | Status (date) | Skill / note |
|---|---|---|---|
| SEC EDGAR via cache and `agent_fetch.py sec` | filings, exhibits, XBRL facts, Forms 3/4/5/144, 13D/G | tested (2026-11-05..08, 7 companies) | `sec-edgar-access`, `sec-insiders-and-holders` |
| SEC full-text search `efts.sec.gov/LATEST/search-index` | phrase search across filings and exhibits; live listing unavailable through `agent_fetch.py` in as-of folders | tested on SNDK (2026-11-05) | `sec-edgar-access` |
| Finviz Elite exports via cache and `agent_fetch.py finviz` | aggregator statements, price history, options snapshot, short-interest history, insiders, news, screener; other exports in API map; as-of fetch permits only daily prices and short-interest history | tested (2026-11-06) except Portfolio; snapshot fields are live, price-history adjustment and historical availability undocumented | `finviz-elite-export`, `ROOT/finviz-api-map.md` |
| FINRA short interest and Reg SHO daily files | dated short positions; separate daily short-sale trade flow | tested (2026-11-05..08); SNDK 2026-10-30 short-interest fetch blocked | `finra-short-interest` |
| US Treasury par yield curve CSV | risk-free rates | tested (2026-11-05) | `other-public-data-sources` |
| FRED `fredgraph.csv?id=<SERIES>` | macro series (no key) | partial: DGS10 tested, terms not reviewed | `other-public-data-sources` |
| Earnings-call transcripts: stockanalysis.com (provider Quartr) | transcripts per ticker; check whether Q&A is present | partial: SNDK only; other tickers untested | `earnings-call-transcripts-and-audio` |
| Company IR sites and webcast players | releases, presentations, audio | mostly blocked (Cloudflare/Akamai/registration); AMD IR works | `playwright-browsing`, `earnings-call-transcripts-and-audio` |
| TrendForce public NAND/DRAM price tables | latest snapshot only, no unit printed | partial (2026-11-05) | `nand-price-sources` |
| DRAMeXchange prices | memory prices | blocked (member login) | `nand-price-sources` |
| USAspending recipient autocomplete | federal awards (recipient name search) | partial: autocomplete tested, award endpoints untested | `other-public-data-sources` |
| ClinicalTrials.gov API v2 | trials | tested (2026-11-05) | `other-public-data-sources` |
| openFDA | drug labels (not a complete regulatory record) | tested (2026-11-05) | `other-public-data-sources` |
| California EDD WARN workbook | layoff notices (rolling window) | tested (2026-11-05) | `other-public-data-sources` |
| House Clerk disclosure index | congressional financial disclosures | partial: index reachable, not parsed | `other-public-data-sources` |
| Senate efdsearch, ImportYeti | disclosures, shipments | blocked | `other-public-data-sources` |
| BIS export controls, OFAC, USTR, customs data, UN Comtrade, EIA, Census, industry bodies | geopolitical and industry series | untested; verify current rule/date and company exposure before conclusions | none yet |
| Foreign filers' home registries (Japan, Korea, Taiwan) | local filings | untested | none yet |
| Options history, borrow fees, TRACE bond trades | positioning and credit | no source configured | gaps |
| Web search / page-summary tools, if available | discovery, not original document evidence | partial; availability depends on agent tools, unreliable on absence | `research-tool-caveats` |

For each new source, log URL, access time, observed publication date, period, unit, coverage, origin and any failed cross-check under "New sources". Mark untested limitations explicitly. No fixed source count substitutes for coverage of the material questions.
