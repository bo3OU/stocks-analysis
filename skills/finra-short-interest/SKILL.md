---
name: finra-short-interest
description: Get FINRA bi-monthly short interest and daily short-sale volume files and read them correctly. Use for the short-interest and positioning checks of a stock analysis.
---

# FINRA short interest and short-sale volume

Both are plain files on `cdn.finra.org`; plain `curl` worked with no key.

## Short interest (bi-monthly)
- URL pattern: `https://cdn.finra.org/equity/otcmarket/biweekly/shrtYYYYMMDD.csv`, where the date is the settlement date (mid-month and month-end). Pipe-delimited despite the `.csv` name. The 2026-10-15 file was available (2.7 MB). The 2026-10-30 file returned 403 AccessDenied on 2026-11-05, because it was not yet published. Publication lags settlement by several business days; record both dates.
- Columns: `accountingYearMonthNumber, symbolCode, issueName, issuerServicesGroupExchangeCode, marketClassCode, currentShortPositionQuantity, previousShortPositionQuantity, stockSplitFlag, averageDailyVolumeQuantity, daysToCoverQuantity, revisionFlag, changePercent, changePreviousNumber, settlementDate`.
- SNDK, settlement 2026-10-15: 4,704,783 shares short, previous 4,819,278 (-2.38%), average daily volume 8,315,919, `daysToCoverQuantity` 1.0. Shares/ADV is 0.57, so FINRA's field looks floored at 1.0: compute days-to-cover yourself and state the method. Finviz showed Short Float 3.35% and Short Ratio 0.44 on its own float and volume definitions, so do not mix the figures.
- Watch `stockSplitFlag` and `revisionFlag`; a split (SNDK's 8-for-1 on 2026-11-19) will make pre-/post-split share counts incomparable.

## Daily short-sale volume (Reg SHO)
- URL pattern: `https://cdn.finra.org/equity/regsho/daily/CNMSshvolYYYYMMDD.txt` (pipe-delimited: `Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market`). Files for 2026-11-04 and 2026-11-05 were available.
- SNDK 2026-11-05: ShortVolume about 3.77M of TotalVolume about 13.99M. Volumes were fractional numbers, and the `Market` field read `B,Q,N` (FINRA-reported trading facilities). Show the venue coverage and denominator. This is trade flow, not short interest: do not sum it into open positions or infer a net bearish bet.

## Not covered
Borrow fees and utilization (no accessible source found), options data (no source tested).
