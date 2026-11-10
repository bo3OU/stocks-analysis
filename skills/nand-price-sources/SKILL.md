---
name: nand-price-sources
description: Where to find public NAND flash price data for memory/storage company analysis (SanDisk, Micron, Kioxia, etc.) and what the public pages do and do not show.
---

# NAND price sources (checked 2026-11-05)

## TrendForce public price pages (reachable with the Playwright MCP)
- Spot: `https://www.trendforce.com/price/flash/flash_spot`
- Contract: `https://www.trendforce.com/price/flash/flash_contract`
- Wafer spot: `https://www.trendforce.com/price/flash/wafer_spot`
- Other pages in the same menu: wafer contract, memory card spot, PC-client OEM SSD contract, SSD street, eMMC spot, eMMC/UFS contract.

What they show: a table with the latest snapshot and a "Last Update" timestamp (GMT+8), plus monthly report teasers. Observed:
- Wafer spot, last update 2026-10-26 14:40: 512Gb TLC session average 16.883 (-9.19%); 256Gb TLC 18.365 (0.00%); 128Gb TLC 9.967 (0.00%).
- Contract, last update 2026-09-30: 128Gb MLC 30.608, 64Gb MLC 23.528, 32Gb MLC 18.208 (niche small-density MLC, not representative of enterprise or consumer TLC/QLC mix).

Limits:
- No unit is printed in the tables. Do not assume USD or per-wafer vs per-Gb without confirming from TrendForce documentation.
- Only the latest snapshot is in the table. History sits behind chart icons that were not extracted. This is not a time series.
- Report summaries are TrendForce's claims (for example the Oct 2026 wafer-contract teaser: prices flat across MLC/TLC/QLC on weak consumer demand and elevated wafer costs). Only the teaser was read, not the full report.
- Pages can lag by days to weeks. Always show the "Last Update" stamp next to any figure.

## DRAMeXchange
Price pages redirect to a member login. Not accessible without membership. Do not bypass it.

## Not checked
Company-disclosed realized prices and bit-shipment/ASP commentary (earnings releases and calls), other price trackers, and Korean/Taiwanese export data.
