---
name: sec-insiders-and-holders
description: Parse SEC Forms 3/4/144, Schedule 13D/G and 13F for insider activity and holders. Use after sec-edgar-access is set up. Covers where the raw XML lives, what fields to read, and what these forms cannot show.
---

# Insiders and holders from EDGAR

Use the `sec-edgar-access` skill for headers, rate limits and caching.

## Finding the filings
In the issuer's submissions JSON, filter `form` for `4`, `3`, `144`, `SCHEDULE 13G`, `SCHEDULE 13G/A`. SNDK's recent list held Form 4 x117, Form 3 x15, Form 144 x24, 13G x7, 13G/A x13. `primaryDocument` for these starts with an `xsl...` folder (rendered HTML). The raw XML is the same path without that folder, i.e. just the file name (`edgardoc.xml` or `primary_doc.xml`).

## Form 4 (verified)
Parse with lxml. Useful paths: `reportingOwner/reportingOwnerId/rptOwnerName`, `officerTitle`, each `nonDerivativeTransaction` with `transactionDate/value`, `transactionCoding/transactionCode`, `transactionAmounts/transactionShares/value`, `transactionPricePerShare/value`, `transactionAcquiredDisposedCode/value`, `postTransactionAmounts/sharesOwnedFollowingTransaction/value`; also `footnote` text and `aff10b5One` (1 = trade under a Rule 10b5-1 plan). Example read: a Chief Legal Officer sold 600 shares on 2026-11-02 at $1,158.26 (code S) under a 10b5-1 plan adopted 2026-03-04, per the filing footnote. Derivative transactions (`derivativeTransaction`) were not parsed. Distinguish codes: S (open-market sale), P (purchase), M (exercise), A (award), F (tax withholding).

## Form 144 (verified)
Fields: `nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold`, `noOfUnitsSold`, `aggregateMarketValue`, `approxSaleDate`, `planAdoptionDate`. It is a notice of a proposed sale, not an executed trade. Its aggregate market value is an estimate at notice time: one SNDK notice implied $1,519.97/share while Finviz's high/low range that day was $1,564.50 to $1,625.36. Do not use it as an execution price or as a price cross-check.

## Schedule 13G/A (verified)
Raw XML tags (use `local-name()` XPath): `reportingPersonName`, `classPercent`, `soleVotingPower`, `sharedVotingPower`, `amendmentNo`. Example: a 13G/A filed 2026-10-27 (amendment 4) reported BlackRock at 7.7% with sole voting power 10,088,654. A 13G/A is a snapshot as of its own event date, filed with a lag, and does not show current holdings.

## 13F (partly tested)
- 13F is filed by managers, not the issuer. EDGAR full-text search with `forms=13F-HR` for `"SANDISK"` between 2026-08-01 and 2026-11-05 returned 2,097 documents. That is documents containing the string, not a ranked holder list, and the name can match other securities. Map by CUSIP.
- Quarterly 13Fs are due about 45 days after quarter-end, so the latest complete period around early November is the 30 June quarter. Verify before relying on it.
- Not tested: parsing a 13F information table, N-PORT. A 13F shows only long US-listed positions at quarter-end, not shorts, trade dates or motives.
