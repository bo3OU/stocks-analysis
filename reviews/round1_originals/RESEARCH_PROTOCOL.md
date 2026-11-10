# Research protocol (agents that search outside the cache: management, market, geopolitics, competition, challenger)

Read `CONTRACT.md` first. This adds how to search, rank sources and avoid wasted work.

## 1. Order of work
1. Read `ROOT/agents/SOURCE_LIBRARY.md`. Use sources marked **tested** first. They have known URLs, quirks and limits. Do not rediscover them.
2. Check what the cache and other agents already hold (`INVENTORY.md`, `PRIOR_FINDINGS`) so you do not repeat their work.
3. Write down your questions and which source family can answer each before searching.
4. Primary documents first (filings, regulator pages, the customer's or supplier's own disclosures, government datasets with methodology), then independent specialist reporting, then everything else.
5. For each material gap try one primary route and one reasonable alternative, log both, then stop. Do not pretend to exhaust the internet.

## 2. Source ladder and independence
- Prefer the source authoritative for the specific claim: filings for reported accounts, a regulator for its decisions, a customer for its own purchasing, a data provider for its documented series.
- A company release, its newswire copy and articles repeating it are one origin. Count origins, not links. Show breadth across origins, not a raw source count.
- Competitor, customer and analyst statements are attributable evidence with incentives (CLAIM), not independent proof. Company-sponsored market sizes are CLAIMs; check the market definition.
- Independent corroboration is needed for disputed claims and consequential inferences. A single authoritative source can establish a directly reported fact.
- Read the strongest evidenced criticism and the company's response. Attribute opinions and allegations; an allegation is not a finding.

## 3. Tools and their limits (details in the skills)
- `WebSearch` finds candidates; its answer about *absence* is unreliable (it said no transcript existed when one did). `WebFetch` returns a small model's summary of a page, not verbatim text: never quote it as a verbatim quotation; for exact text download the page with `curl` (default User-Agent, no spoofing) into `work/downloads/` and read it.
- If the Playwright browser tools are available (`mcp__playwright__browser_*`), use text snapshots, not screenshots, except to verify a visual figure. Many investor-relations sites (Cloudflare, Akamai) and webcast players (registration forms) block automation: record `blocked` and move on. Do not fill registration forms, log in, or bypass anything.
- Cached documents and `agent_fetch.py` for SEC and Finviz. Other sites: `curl -sS -L -m 30` with the default User-Agent, saved under `work/downloads/`, one request at a time.
- PDFs: `pdftotext -layout` and `pdftoppm -png -r 150` (poppler is installed); view the PNG to verify tables.
- Record each retrieval: URL, retrieval time, the page's own "last updated" or publication date, units and geography. A page snapshot is a point in time, not a series.

## 4. Quality rules
- Tie every finding to a research question. Weight conclusions by evidence quality and materiality; the record may be asymmetric, so do not force balance. Say what each side gets right, what is unproven, and which facts would change the conclusion.
- Use the INFERENCE table (CONTRACT section 6) for material interpretations. Alternatives are hypotheses unless supported; label them.
- Do not use job ads as demand evidence, trading as motive evidence, or timing as proof of cause. A benchmark moving does not prove a company-specific effect: explain the company's actual exposure (contract lags, pass-through, hedging) or mark it UNKNOWN.
- A source you found yourself is **untested** until you verified that it is reachable, shows a date and unit, and matches a figure you can check elsewhere. Untested sources cannot support a material conclusion alone; list them under "New sources" in `search_log.md`.
- Stop when new searches only return the same origins, when the questions are answered or shown unanswerable with the available public sources, or when your agent file's stop condition is met. Report unfinished work and its likely effect.
