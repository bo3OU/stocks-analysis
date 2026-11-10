---
name: other-public-data-sources
description: Public rate series, government-award, trial, FDA, layoff-notice and disclosure sources checked for stock analysis, with the quirks found. Use only when the data is material to the company being analyzed.
---

# Other public data sources (checked 2026-11-05/06)

## Rates (no key)
- Treasury daily par yield curve CSV: `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv`. Newest row first, columns 1 Mo to 30 Yr in percent. On 2026-11-05 the 10 Yr was 4.84.
- FRED series CSV without an API key: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10` (full history, 269 KB). Its last rows were 2026-11-03 and 2026-11-04, one day behind Treasury. FRED terms were not reviewed. Match Treasury and credit comparisons by date and duration.

## Government awards
USAspending recipient autocomplete: `POST https://api.usaspending.gov/api/v2/autocomplete/recipient/` with `{"search_text":"sandisk","limit":3}` returned `count: 0` (plus a deprecation message about `recipient_level`). That means no match in this autocomplete for that name, not proof of no government business. Award search endpoints, subsidiaries and aliases were not tested.

## Healthcare and regulatory (not relevant to SNDK, but checked)
- ClinicalTrials.gov v2: `https://clinicaltrials.gov/api/v2/studies?query.spons=<name>&pageSize=1&fields=NCTId,BriefTitle,OverallStatus` worked. `query.spons=Moderna` returned a study coded VX-522 (a Vertex/Moderna collaboration program as I recall), so the sponsor filter seems to match collaborators. Request the sponsor fields and check the lead sponsor before attributing a trial.
- openFDA: `https://api.fda.gov/drug/label.json?search=openfda.brand_name:lipitor&limit=1` worked; its `meta.disclaimer` says results are unvalidated. It is not a complete regulatory record. Use the FDA's approval and clearance databases for approvals.

## Layoff notices
California EDD WARN workbook: `https://edd.ca.gov/siteassets/files/jobs_and_training/warn/warn_report1.xlsx` (found via a link on the EDD WARN page). Five sheets; the detailed sheet's table starts at row 2 and covered only 07/01/26 to 11/04/2026 (a rolling window, 459 rows), updated Tuesdays and Thursdays. No Sandisk or Western Digital rows matched. That is no matching record in this window, not proof of no layoffs. Other states were not tested.

## Political disclosures
House Clerk annual index zip exists (`https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2026FD.zip`, HEAD returned 200, last modified 2026-11-05); contents were not parsed. The Senate search site returned 403 to curl. Low priority for business economics.

## Not reachable or not tested
ImportYeti (Cloudflare challenge), company careers pages (my guessed SanDisk careers URL was a 404), options chains, borrow fees, bond trades (TRACE), foreign issuer filings (Kioxia in Japan, SK hynix in Korea; Samsung's IR landing page loads).
