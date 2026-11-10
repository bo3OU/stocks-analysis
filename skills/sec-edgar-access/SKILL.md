---
name: sec-edgar-access
description: Fetch SEC EDGAR data (ticker to CIK, filing lists, filing documents and exhibits, XBRL facts and frames, full-text search) with a declared User-Agent and within SEC fair-access limits. Use curl or Python, not a browser.
---

# SEC EDGAR access

## Declared User-Agent (required)
`SEC_USER_AGENT` is in `~/Workspace/personal/trading/fundamental-analyser/.env`:

```bash
set -a; . ~/Workspace/personal/trading/fundamental-analyser/.env; set +a
curl -sS --compressed -H "User-Agent: $SEC_USER_AGENT" URL
```
A browser-style User-Agent is not acceptable to the SEC. Do not spoof one and do not change the declared contact without the user's say-so.

## Rate and caching
The SEC's published limit is 10 requests/second in total across all workers. Stay far below it (about 2 requests/second was used in testing), retry a bounded number of times, honor Retry-After, and cache every response. Check sec.gov/developer for the current limit.

## Browsers are blocked
Headless Chrome got HTTP 403 "Undeclared Automated Tool" on sec.gov. Use curl or Python.

## Verified endpoints
- Ticker to CIK: `https://www.sec.gov/files/company_tickers.json` (SNDK = CIK 2023554; MU 723125; WDC 106040; STX 1137789).
- Filing list: `https://data.sec.gov/submissions/CIK##########.json` (10-digit zero-padded). `filings.recent` holds parallel arrays: `form`, `filingDate`, `reportDate`, `accessionNumber`, `primaryDocument`, `items`, `acceptanceDateTime` (UTC). For SNDK `filings.files` (older pages) was empty. For bigger issuers expect extra pages listed there.
- XBRL facts: `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`.
- XBRL frames (cross-company, one period): `https://data.sec.gov/api/xbrl/frames/us-gaap/<Tag>/USD/CY2025Q3.json`.
- Filing documents: `https://www.sec.gov/Archives/edgar/data/<CIK>/<accession-no-dashes>/<file>`; the folder listing is `.../<accession-no-dashes>/index.json`.
- Full-text search: `https://efts.sec.gov/LATEST/search-index?q=%22phrase%22&ciks=0002023554&forms=10-K,10-Q` (add `&dateRange=custom&startdt=YYYY-MM-DD&enddt=YYYY-MM-DD`). JSON: `hits.total.value`, and each hit has `_id` = `accession:filename`, `_source.file_date`, `form`, `display_names`. Hits include exhibits, so counts are documents, not mentions (SNDK "Kioxia" in 10-K/10-Q: 12 documents, including a 10-Q exhibit agreement).

## Working with filings
- An 8-K's primary document is often a 5 KB cover page. The substance is in exhibits listed in `index.json`. For SNDK's 2026-10-29 8-K (items 2.02, 8.01, 9.01) the exhibit `sndkq1-27ex991xpressrelease.htm` was the earnings release, not a call transcript. Open each exhibit and confirm what it is.
- 8-K `items` field: `2.02` = results of operations (earnings release). Use it with `acceptanceDateTime` to find earnings events and the right trading session.
- Inline-XBRL `.htm` filings (Workiva) are large (10-Q: 1.16 MB). Convert to text with BeautifulSoup/lxml and table rows joined by ` | `; a harmless `XMLParsedAsHTMLWarning` appears. Minimal converter:

```python
import sys
from bs4 import BeautifulSoup
soup = BeautifulSoup(open(sys.argv[1], "rb").read(), "lxml")
for t in soup(["script", "style"]): t.decompose()
for tr in soup.find_all("tr"):
    cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
    tr.replace_with(soup.new_string(" | ".join(c for c in cells if c) + "\n"))
lines = [l.strip() for l in soup.get_text("\n").splitlines()]
open(sys.argv[2], "w").write("\n".join(l for l in lines if l))
```
  Run as `python -I converter.py in.htm out.txt` from a directory other than the download folder. Then grep for the income statement, MD&A, liquidity and notes.
- Reconciliation worked: SNDK quarter ended 2026-10-02 revenue was $11,031M in both the XBRL company facts and the 10-Q income statement (prior-year quarter $2,308M). Companyfacts labels it `fy2027 Q1`; the 10-K year ended 2026-07-03 is `fy2026 FY`. Still read the filing for units, scope and restatements.
- Submissions `fiscalYearEnd` (SNDK "0628") differs from the actual 52/53-week period ends (2026-07-03, 2026-10-02). Use the period end printed in the filing.
- Frames caveats: Micron did not appear under `RevenueFromContractWithCustomerExcludingAssessedTax` (it uses another revenue tag, so try `Revenues`); frames place fiscal quarters into the nearest calendar frame (WDC, STX and SNDK quarters ending 2026-10-02/2025-10-03 all landed in the same frame, others may not); my jq printed `null` for `filed`/`fy`/`fp`, so inspect the actual field names before relying on them.
- Companyfacts for a recent spin-off (SNDK) is short; historical series before the spin sit with the former parent and are not comparable.
