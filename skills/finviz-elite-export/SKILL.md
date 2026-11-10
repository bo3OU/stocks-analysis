---
name: finviz-elite-export
description: Pull price history, screener/peer data, valuation/ownership/financial views, consensus fields and ticker news from Finviz Elite's authenticated CSV exports. Use for daily prices, peer discovery, and cross-checks. Not for scraping finviz.com pages.
---

# Finviz Elite exports

The account owner has a paid Finviz Elite subscription. Use only the authenticated export endpoints below. Do not scrape finviz.com HTML pages.

## Token
`FINVIZ_AUTH_TOKEN` is in `~/Workspace/personal/trading/fundamental-analyser/.env`:

```bash
set -a; . ~/Workspace/personal/trading/fundamental-analyser/.env; set +a
```

Reference `$FINVIZ_AUTH_TOKEN` in commands. Never print it or write it (or a URL containing it) anywhere. Record URLs as `auth=<redacted>`.

## Verified endpoints (host `elite.finviz.com`, no `.ashx`; the `.ashx` URLs 301-redirect here)

Daily price history CSV (`Date,Open,High,Low,Close,Volume`; dates MM/DD/YYYY):
```bash
curl -sS "https://elite.finviz.com/quote_export?t=TICKER&p=d&auth=$FINVIZ_AUTH_TOKEN"
```
SNDK returned 435 rows from 2025-02-13 (its listing) to the latest close.

Screener/overview exports (`export?v=<view>&t=TICKER`; add Finviz screener filters for peer discovery):

| `v=` | Columns |
|---|---|
| 111 | No., Ticker, Company, Sector, Industry, Country, Market Cap, P/E, Price, Change, Volume |
| 121 | Valuation: P/E, Forward P/E, PEG, P/S, P/B, P/Cash, P/FCF, EPS growth fields, Sales growth past 5Y |
| 131 | Ownership: Shares Outstanding, Shares Float, Insider/Institutional Ownership and Transactions, Short Float, Short Ratio, Average Volume |
| 141 | Performance: week to 10 years, volatility, relative volume |
| 161 | Financial: dividend yield, ROA/ROE/ROIC, current/quick ratio, debt/equity, margins, Earnings Date |

Custom view with many columns: `export?v=152&t=TICKER&c=1,2,3,...,90` (column IDs 1 to 90 all returned 90 columns). Fields seen include: Target Price, Analyst Recom, EPS (ttm), EPS Next Q, EPS/Sales growth, Shares Outstanding and Float (millions), Insider/Institutional Ownership, Short Float, Short Ratio, Short Interest (millions), Beta, 52-week high/low (as % from price), Earnings Date (with time), IPO Date, Employees, Optionable, Shortable, Sales. Column order and names come from the header row; read the header, do not assume positions.

Ticker news CSV (`Title,Source,Date,Url,Category,Ticker`):
```bash
curl -sS "https://elite.finviz.com/news_export?v=3&t=TICKER&auth=$FINVIZ_AUTH_TOKEN"
```
Without `t=` it returns market-wide news. With `t=` it still included articles only loosely related to the ticker (for example a Nvidia headline). It is a headline feed, not a vetted set of company news.

## Full API map (verified 2026-11-06)
The complete, tested map is in `~/Workspace/personal/trading/fundamental-analyser/finviz-api-map.md` (read it before calling anything beyond the basics here). It was built from the logged-in Elite docs at `elite.finviz.com/apis` (25 pages) plus a real call to every endpoint family.
- **Rate limit: 10 requests per rolling 5 seconds, shared across all export endpoints.** HTTP 429 with `Retry-After: 5` when exceeded. Use about 1 request/second and `curl -L`.
- **Pattern:** page URL with `export/` inserted, plus `&auth=$FINVIZ_AUTH_TOKEN`. All returned `text/csv`.
- **Stock exports** (`export/stock?t=<T>&ty=<code>`): omitted or `c` price history (`p=d`, `r=d1|d5|m1|m3|m6|ytd|y1|y2|y5|max`), `oc` options chain (`e=` expiry, `s=` strike), `lf` latest SEC filings (`f=` category, `o=` sort), `si` FINRA short-interest history (all settlement dates), `statements` (`s=IA|IQ|BA|BQ|CA|CQ`, `order=`, `growth=`).
- **Other exports:** `screener` (`type=stocks|etf&v=&f=&c=`), `insiders` (max 200 rows; last 7 days unless filtered by ticker or owner CIK), `news` (max 100 rows), `groups`, `calendar/earnings|dividends|economic`, `futures|forex|crypto/performance`, `funds` and `funds/<id>/holdings`, `managers` and `managers/<id>/holdings` (13F-type, no ticker filter), `portfolio` (not tested).
- **Useful for stock analysis:** statements (cross-checked against the 10-K/10-Q), short-interest history (matches FINRA), options chain (current snapshot), insider transactions with Form 4 links, latest filings with SEC URLs, and the earnings calendar (EPS and revenue estimate/actual/surprise and a 1-day price reaction that matched my close-to-close calculation).
- **Not in the API:** the analyst ratings table (per-firm rating and target changes) and consensus analyst counts. Only Target Price and Recom exist (screener custom view `v=152`).
- The docs page shows the account token in plain text. Never paste docs text or screenshots into notes.

## Caveats found
- **Aggregator.** Use for discovery, peers and cross-checks. Reconcile material figures to primary sources. Provenance of Target Price, Analyst Recom and EPS estimates (provider, date, number of analysts) is not shown: label them as unattributed aggregator figures, not dated consensus.
- **Units:** Shares and Short Interest columns are in millions (SNDK Short Interest 4.70 matched FINRA's 4,704,783 shares). Market Cap in the screener and calendar exports is in millions of USD (SNDK 114,746 = $114.7B, matching the page).
- **Adjustment basis of history is undocumented.** One AAPL check suggested split-adjusted but not dividend-adjusted. SNDK's 2026-11-02 Form 4 sale price ($1,158.26) fell inside Finviz's high/low range for that day, which is consistent with unadjusted prices before a split.
- **Corporate actions:** SanDisk announced an 8-for-1 forward split effective 2026-11-19 (company release, 2026-10-29). Expect the history to be rebased after the effective date (not yet observed). Stamp every cached CSV with its download date and re-download after any split.
- **History length equals time since listing** (SNDK: 7 earnings events, not 12). Pre-spin history belongs to the former parent and is a different entity.
- Make requests sequentially at a modest rate. Cache CSVs in the research directory.
- **Earnings-reaction recipe (worked):** take 8-Ks with item 2.02 from the SEC submissions JSON, convert `acceptanceDateTime` (UTC) to New York time; if accepted after 16:00 ET the reaction session is the next trading day, otherwise the same day; compare that close to the prior close. This is a price move after an announcement, not proof of cause: compare with market/sector moves and look for confounding news.

## Reconciled against the Finviz quote page (user screenshots, SNDK, 2026-11-05 close)
- **Matched exactly:** price 806.43, previous close 1037.40, change -22.26%, EPS ttm 124.75, EPS next Q 56.97, EPS/Sales growth fields, shares outstanding 144.00M, float 140.42M, insider/institutional ownership and transactions, short float 3.35%, short ratio 0.44, short interest 4.70M, beta 5.63, 52-week high/low, Recom 1.47, Target Price 2168.80, IPO date, employees, earnings date (page "Oct 29 AMC" = export "10/29/2026 4:30:00 PM"), news headlines and times (ET). Daily volume differed slightly (page 30,362,705 vs CSV 30,258,502, cause unknown).
- **On the page, and now found in the API:** FactSet statements (`ty=statements`) and short-interest history (`ty=si`), which matched the filings and FINRA. **On the page, not in the documented API:** the analyst ratings table and the 15/1/0 distribution, peers, ETF holders, correlations, and price-tagged news.
- **"EPS Q/Q" and "Sales Q/Q" are year-over-year.** Sales Q/Q 377.95% = 11,031 / 2,308 (quarter vs the same quarter a year earlier, per the 10-Q). Sequential growth was about 23% (company release).
- **Short ratio and short float depend on the view.** Page header: 4.70M / 140.42M float = 3.35% and 4.70M / 10.63M average volume = 0.44 (current float and average volume). History table row for settlement 2026-10-15: 3.30% and 0.38 (4.70M / 142.63M float, 4.70M / 12.48M average volume at that date). FINRA's own average daily volume for that date was 8.32M. State which denominator you use.
- **"Implied Upside" in the ratings table is target / today's price - 1**, not upside at the time of the rating (every row checked: e.g. 2400 / 806.43 = +197.6%). The consensus target averages targets of different ages (newest row 2026-09-22, some from April 2026) and predates the large price drop. Treat it as an undated, unattributed aggregator figure.
- **Market cap implies a different share count:** 114.75B / 806.43 is about 142.3M shares vs the 144.00M shown. Share counts look rounded to whole millions in the page's chart (145.00, 145.00, 146.00, 146.00, 144.00). Take per-share math and share counts from the filing cover and notes.
- **FactSet fiscal dates are normalized:** the page shows FY2026 ending 6/30/2026, but the filing says 7/3/2026. Revenue matched the filing (FY2026 20,248) and the TTM figure reconciles: 20,248 + 11,031 - 2,308 = 28,971. Take period ends from the filing.
