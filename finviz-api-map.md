# Finviz Elite API map

Source: the logged-in Elite docs at `https://elite.finviz.com/apis` (25 pages crawled on 2026-11-06 with Playwright, "Show More" / "Learn More" panels expanded), plus a real call to every endpoint family on 2026-11-06 (SNDK where a ticker was needed). The token is not stored here: it is `FINVIZ_AUTH_TOKEN` in `.env`.

## Global rules (from the docs)
- Base: `https://elite.finviz.com/export/...`, add `&auth=$FINVIZ_AUTH_TOKEN`. Always use `curl -L`.
- Turn any page URL into an export URL by inserting `export/` (details per endpoint below). Legacy `.ashx` URLs still work but return a 301 with an empty body unless redirects are followed.
- **Rate limit: 10 requests per rolling 5-second window, shared by every export endpoint on the account.** Over the limit returns HTTP 429 with `Retry-After: 5`; blocked 429s do not count against the budget. (429 was not triggered in testing; about 1 request/second was used.)
- Every response was `text/csv`. Date formats differ by endpoint (see columns).

## Endpoint map

| Endpoint | URL template (after `export/`) | Row cap | Tested |
|---|---|---|---|
| Screener | `screener?type=stocks\|etf&v=<view>&f=<filters>&c=<cols>` | none stated | Yes |
| Stock: price history | `stock?t=<T>&p=d&r=<range>` (same as `ty=c` or no `ty`) | none stated | Yes |
| Stock: options chain | `stock?t=<T>&ty=oc&e=<YYYY-MM-DD>&s=<strike>` | none stated | Yes |
| Stock: latest filings | `stock?t=<T>&ty=lf&f=<category>&o=<sort>` | none stated | Yes |
| Stock: short interest | `stock?t=<T>&ty=si` | none stated | Yes |
| Stock: statements | `stock?t=<T>&ty=statements&s=<IA\|IQ\|BA\|BQ\|CA\|CQ>&order=&growth=` | 8 periods | Yes |
| Insiders | `insiders?t=<T>&tc=&or=&tv=&oc=&o=` | 200 rows | Yes |
| News | `news?v=<1-5>&c=&pid=&t=` | 100 rows (stocks, ETFs, crypto views) | Yes |
| Groups | `groups?g=<group>&v=<view>&o=&c=` | none stated | Yes |
| Calendar: earnings | `calendar/earnings?dateFrom=&dateTo=&sort=` | range max 90 days | Yes |
| Calendar: dividends | `calendar/dividends?dateFrom=&dateTo=&sort=` | range max 90 days | Yes |
| Calendar: economic | `calendar/economic?dateFrom=&dateTo=` | range max 365 days | Yes |
| Futures performance | `futures/performance?sort=` | | Yes |
| Forex performance | `forex/performance?unit=pct\|pips&sort=` | | Yes |
| Crypto performance | `crypto/performance?c=USD\|USDT\|EUR\|BTC&sort=` | | Yes |
| Funds list | `funds?search=&sort=` | 500 rows | Yes |
| Fund holdings | `funds/<name-slug-ID or S0000xxxxx>/holdings?reportEndDate=&transactionType=&assetCategory=&sort=` | none | Yes |
| Managers list | `managers?search=&sort=` | 500 rows | Yes |
| Manager holdings (13F) | `managers/<name-slug-ID or numeric ID>/holdings?reportEndDate=&transactionType=&optionType=&sort=` | none | Yes |
| Portfolio | `portfolio?pid=<id>&o=&c=<cols>` | | **No** (needs your portfolio id) |

## Details and results

### Screener
- Page `screener/stocks?v=111&f=fa_div_pos,sec_technology` becomes `export/screener?type=stocks&v=111&f=fa_div_pos,sec_technology` (use `type=etf` for the ETF screener; without `type` you get stocks and ETFs together).
- `c=` picks columns for the Custom view: open the Custom view, Customize, save, copy `c` from the URL. Docs example: `v=151&c=0,1,2,3` = No., Ticker, Company, Sector. Earlier I found `v=152&t=<T>&c=1,2,...,90` returns 90 named columns.
- Tested `type=stocks&v=111&f=sec_technology,cap_largeover`: 154 rows; columns No., Ticker, Company, Sector, Industry, Country, Market Cap, P/E, Price, Change, Volume. Market Cap is in millions of USD (matches the earnings calendar's Market Cap).
- Older view codes tested earlier on the legacy path: `v=111` overview, `121` valuation, `131` ownership, `141` performance, `161` financial.

### Stock (one ticker per request; `ty` selects the dataset)
`ty=c` or omitted = price history, `ty=oc` = options, `ty=lf` = latest filings, `ty=si` = short interest, `ty=statements` = statements.

- **Price history** `p=d`; `r` range: `d1, d5, m1, m3, m6, ytd, y1, y2, y5, max`. Columns Date (MM/DD/YYYY), Open, High, Low, Close, Volume. `r=m1` returned 23 rows. Adjustment basis undocumented (see skills).
- **Options** all contracts: 11,456 rows (1.5 MB) for SNDK. Filters `e=YYYY-MM-DD` (expiry) and `s=<strike>` (decimals allowed) match exactly and the filtered column is omitted. `e=2026-11-20` returned 650 contracts. Columns: Contract Name, Last Trade (no timezone), Expiry, Strike, Last Close, Bid, Ask, Change $, Change %, Volume, Open Int., Type, IV, Delta, Gamma, Theta, Vega, Rho. Current snapshot only.
- **Latest filings** `f=` category: `annual-quarterly-current, insider-equity, beneficial-ownership, exempt-offerings, registration-statements, filing-review-correspondence, sec-orders-notices, proxy-materials, tender-offers, trust-indentures`. `o=filingDate|reportDate|form` (prefix `-` for descending). Columns: Filing Date, Report Date, Form, Description, Filing (EDGAR index URL), Document (SEC viewer URL). SNDK with `f=annual-quarterly-current`: 26 rows, newest the 10-Q filed 2026-10-30.
- **Short interest** all FINRA settlement dates, newest first. Columns: Settlement Date (YYYY-MM-DD), Short Interest, Shares Float, Avg. Daily Volume, Short Float, Short Ratio. SNDK: 40 rows from 2025-02-28 to 2026-10-15. The 2026-10-15 row (4,704,783 shares) equals FINRA's own file.
- **Statements** `s=IA` income annual (default), `IQ` quarterly, `BA`/`BQ` balance sheet, `CA`/`CQ` cash flow; `so=R` = Reuters source (default FactSet; `so=R` not tested); `order=newest|oldest`; `growth=yoy,yoy_pct,qoq,qoq_pct` (comma-combinable; qoq only for quarterly). One row per line item, 8 periods, amounts in full units (not thousands), per-share/ratio/percent rows with 2 decimals, no thousands separators, negatives with a minus. Checked against the 10-K/10-Q: FY2026 revenue 20,248,000,000; Q1 FY2027 revenue 11,031,000,000, net income 8,101,000,000, diluted EPS 52.60. Period End Date is normalized (FY2026 shown as 6/30/2026, Q1 2027 as 9/30/2026, while the filings say 7/3/2026 and 10/2/2026).

### Insiders
`t=<ticker>`, `tc=1` buy, `2` sale, `4` option exercise, `7` all (default), `or=10` 10% owners only / `or=-10` exclude, `tv=<min USD>`, `oc=<owner CIK>`, `o=` accepted (default), ticker, transactionValue, transactionDate, transactionPricePerShare, transactionShares, sharesOwnedFollowingTransaction (prefix `-` descending). Max 200 rows; without a ticker or owner CIK only the last 7 days. Columns: Ticker, Owner, Owner CIK, Relationship, Date, Transaction, Cost, #Shares, Value ($), #Shares Total, SEC Form 4 (acceptance time), SEC Form 4 Link. SNDK: 42 rows, including the 2026-11-02 sale of 600 shares at $1,158.26, identical to the EDGAR Form 4. Transaction codes are collapsed to Buy/Sale/Option exercise; the 10b5-1 flag and footnotes are not in the CSV (use the Form 4 itself).

### News
`v=1` market by time, `v=2` market by source (with `c=1` news only or `c=2` blogs only), `v=3` stocks feed, `v=4` ETFs feed, `v=5` crypto feed, `pid=` portfolio news, `t=MSFT,AAPL` ticker filter (comma list; stocks and crypto). Columns Title, Source, Date (YYYY-MM-DD HH:MM:SS, ET as far as seen), Url, Category, Ticker. `v=3&t=SNDK` returned 100 rows (the cap).

### Groups
`g=sector|industry|country|capitalization`, `v=<view>` (docs example `g=sector&v=152`), `o=` sort, `c=` columns. `g=sector&v=152` returned 11 rows: No., Name, Market Cap, P/E, Dividend Yield, Average Volume, Change, Volume, Stocks.

### Calendar
- **Earnings** `dateFrom` (required), `dateTo` (max 90 days after), `sort=` earningsDate (default), ticker, company, -marketCap, epsEstimate, epsActual, epsSurprise, epsReportedEstimate, epsReportedActual, epsReportedSurprise, salesEstimate, salesActual, salesSurprise, oneDayPriceReaction. Columns: Date (YYYY-MM-DD HH:MM, ET), Ticker, Company, Market Cap (millions USD), EPS Estimate, EPS Actual, EPS Surprise, EPS GAAP Estimate/Actual/Surprise, Revenue Estimate/Actual/Surprise (millions), 1-Day Price Reaction (%). 2026-10-26 to 2026-10-30 returned 820 rows. SNDK row: reported 2026-10-29 16:30, EPS actual 49.51 vs estimate 46.67 (+6.09%), GAAP EPS 52.60, revenue 11,031 vs 10,718.39 (+2.92%), 1-day reaction -13.47%, which equals the close-to-close move computed from the price history (1,330.05 to 1,150.89). Estimate provenance is not given.
- **Dividends** `dateFrom` required, `dateTo` max 90 days, `sort=` ticker (default), company, exdate, -ordinary, -special, -yield. Columns: Ticker, Company, Ex-Date, Amount, Special, Dividend Est. Yield. 2026-11-09 to 11-13: 376 rows.
- **Economic** `dateFrom` snaps to the Monday of that week; without `dateTo` one Mon-Fri week; `dateTo` max 365 days after. Columns: Event, Date, Time, Impact, For, Actual, Expected, Prior (values are text such as "-1.9%"). Week of 2026-11-02: 89 rows.

### Futures, Forex, Crypto performance
`sort=` one of `-perfDayPct` (default), `ticker`, `name`, `-last`, `-perf5minPct`, `-perfHourPct`, `-perfWeekPct`, `-perfMonthPct`, `-perfMtdPct`, `-perfQuarterPct`, `-perfHalfYearPct`, `-perfYtdPct`, `-perfYearPct` (rows with no value always last). Forex: `unit=pct` (default) or `unit=pips` (then sort values end in `Pips`). Crypto: `c=USD` (default), `USDT`, `EUR`, `BTC`. Columns: No., Ticker, Name, Price, Performance (5 Minutes, 1 Hour, Day, Week, Month, Month To Date, Quarter, Half Year, Year To Date, Year). Rows: futures 60, crypto 40, forex 10.

### Funds (N-PORT style data)
- List: `search=` partial match on fund or series name; `sort=` -most_popular (default), -portfolio_value, -num_investments, -new_purchased, -sold_out, -added, -reduced, -top_ten_concentration, -turnover, -time_held_top10, -time_held_all. Capped at 500 rows. Columns: Name, Series Name, Investor ID, Report Date, Portfolio Value, # Investments, New Purchased, Sold Out, Added, Reduced, Top 10 Concentration (%), Turnover (%), Time Held Top 10, Time Held All. `search=fidelity` returned 500 rows.
- Holdings: path uses either `<name-slug>-<ID>` or just the series ID (`S000007195`), e.g. `export/funds/S000007195/holdings`. `reportEndDate=YYYY-MM-DD`, `transactionType=new|added|reduced|closed_out|no_change`, `assetCategory=EC|EP|DBT|STIV|LON|ABS-MBS|DCR|DE|DIR|DFE|DCO|DO|RA|SN|ABS-APCP|ABS-CBDO|ABS-O|COMM|RE`, `sort=` -valueUsd (default), issuerTicker, issuerName, assetCategory, shares, shareType, percentageOfPortfolio, previousPercentageOfPortfolio, percentChangeFromPrevious, payOffProfile, investmentCountry. Columns: Ticker, Name, Asset Category, Balance, Units, Market Value, % Portfolio, Prev. % Portfolio, % Change, Payoff Profile, Country. Uncapped (481 rows for the Fidelity Blue Chip Growth Fund).

### Managers (13F)
- List: same `search=` and `sort=` as Funds; capped at 500 rows. Columns: Name, Portfolio Manager, Investor ID, Report Date, Portfolio Value, # Investments, New Purchased, Sold Out, Added, Reduced, Top 10 Concentration (%), Turnover (%), Time Held Top 10, Time Held All. `search=berkshire` returned 10 rows (Berkshire: Investor ID 1067983, Report Date 2026-06-30).
- Holdings: `export/managers/<name-slug>-<ID>/holdings` or `export/managers/1446194/holdings`. `reportEndDate=YYYY-MM-DD`, `transactionType=new|added|reduced|closed_out|no_change`, `optionType=share|put|call`, `sort=` -valueUsd (default), issuerTicker, shares, percentageOfPortfolio, changeInShares, percentChangeFromPrevious, percOwnership. Columns: Ticker, Name, Type (share/Put/Call), Sector, Industry, Shares Held, Market Value, % Portfolio, Prev. % Portfolio, Change in Shares, % Change, % Ownership, Avg. Price, Q 1st Owned. Uncapped: one large manager returned 15,039 rows (2.7 MB); `reportEndDate=2026-06-30&transactionType=new` returned 1,974.
- **There is no ticker filter on holdings.** To find who holds a stock you must pull managers one at a time (within the rate limit), or use SEC 13F/13G sources.

### Portfolio
`portfolio?pid=<id>&o=price&c=0,1,2,3`; column IDs 0 Ticker, 1 Company, 2 Price, 3 Change %, 4 Volume, 5 Transaction, 6 Date, 7 Shares, 8 Cost, 9 Market Value, 10 Gain $, 11 Gain %, 12 Change $. Not tested.

## Not available through this API (as documented)
Analyst ratings table (per-firm rating and price-target history), the consensus analyst count/distribution, peers, ETF holders, correlations, and news items tagged with price moves are on the Stock page but not among the documented Stock exports. Only Target Price and Recom come through the screener custom view (`v=152`).

## Caveats
- Aggregator data: attribute it ("Finviz export, FactSet statements") and reconcile material figures to filings or the primary source. Cross-checks that matched: statements vs 10-K/10-Q, short interest vs FINRA, insider row vs the EDGAR Form 4, earnings reaction vs computed close-to-close.
- FactSet-normalized period ends (see Statements). Statement dollar amounts are in full units; Calendar and Screener market caps and revenue are in millions.
- Options and price timestamps carry no timezone; options are a current snapshot only.
- The docs page itself shows the account token in plain text; do not paste docs screenshots or text containing it.
