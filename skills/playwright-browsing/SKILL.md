---
name: playwright-browsing
description: Use the Playwright MCP (headless Chrome) for JS-rendered pages, clicking through sites and visual checks, and know which sites block automation. Prefer text snapshots over screenshots.
---

# Playwright MCP browsing

Registered at user scope: `npx -y @playwright/mcp@latest --browser chrome --headless`. Its tools appear after a Claude Code restart. During testing the same server was driven over stdio with a small script, which exercised these tools: `browser_navigate`, `browser_snapshot`, `browser_take_screenshot` (args `type`, `filename`, `fullPage`), `browser_wait_for` (`time`), `browser_network_requests` (`static`, `requestBody`, `requestHeaders`).

## How to work efficiently
- Try `curl` or WebFetch first for static pages and APIs. Use the browser when the page needs JavaScript or clicks.
- Read pages with `browser_snapshot` (accessibility tree as text). Each snapshot is saved to a file: grep it for the rows or links you need instead of reading it whole. Ad iframes make snapshots noisy.
- Screenshots only when layout, a chart, or visual verification matters. A cookie-consent overlay may cover the page; snapshots still read the content underneath.
- `browser_network_requests` lists what the page loaded (useful to find a media or data URL). A player page may show nothing useful until play is pressed.

## Site access matrix (tested 2026-11-05/06; plain curl and/or headless Chrome)

| Result | Sites |
|---|---|
| Worked | ir.amd.com (including event pages, press releases), samsung.com/global/ir, newmountainfinance.com IR event page, methanex.com, trendforce.com price pages, sandisk.com press-release pages, stockanalysis.com transcripts, edd.ca.gov, disclosures-clerk.house.gov |
| Cloudflare block (403 for curl, "Just a moment..." challenge for headless Chrome) | investors.micron.com, investor.nvidia.com, investor.apple.com, investors.seagate.com, ir.netflix.net, importyeti.com, elite.finviz.com (headless Chrome only: a visible, logged-in Chrome passed) |
| "Access Denied" 403 (Akamai confirmed for investor.sandisk.com and ir.tesla.com; the others returned the same kind of short error page, vendor not confirmed) | investor.sandisk.com (curl and Chrome), investorcenter.slb.com (curl and Chrome), ir.tesla.com, ir.wabteccorp.com, efdsearch.senate.gov (curl) |
| Login or registration gate | dramexchange.com price pages (member login), edge.media-server.com webcast players (registration form) |
| Declared-UA gate | sec.gov (needs the SEC User-Agent; use curl, not the browser) |
| Not understood / my guess | investors.westerndigital.com and investors.intel.com: curl connection failure (code 000, cause unknown). kioxia.com and skhynix.com IR URLs: 404 on guessed paths (site may be reachable at other paths) |

A block today is not a permanent fact about the company; record it with the date.

**Logged-in browsing (Finviz docs):** a persistent profile at `~/Workspace/personal/trading/fundamental-analyser/.browser-profile` holds a Finviz Elite session. The user logged in by hand in a visible Chrome window launched with `--user-data-dir` pointing at that folder (the agent never sees the password). Reuse needs a visible (not headless) window because Cloudflare challenges headless Chrome on elite.finviz.com. To expand collapsed doc panels and read the text in one call, use `browser_evaluate` with a function that clicks buttons labelled "Show More"/"Learn More" and returns `document.body.innerText`. Page text can include the API token: redact it before saving or showing anything. The profile folder is gitignored; delete it to end the session.

## Evidence rules
Record URL, retrieval time and the page's own "last update" stamp for each figure. A page snapshot is a point-in-time observation, not a historical series.
