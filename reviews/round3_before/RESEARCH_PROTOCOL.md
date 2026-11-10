# Research protocol (agents that search outside the cache: management, market, geopolitics, competition, challenger)

Read `CONTRACT.md` first. This adds how to search, rank sources and avoid wasted work.

## 1. Order of work
1. Read `ROOT/agents/SOURCE_LIBRARY.md`. Prefer a relevant tested route, but verify that its dated test still applies; source status is not current coverage.
2. Check what the cache and other agents already hold (`INVENTORY.md`, `PRIOR_FINDINGS`) so you do not repeat their work.
3. Write down your questions and which source family can answer each before searching.
4. Primary documents first (filings, regulator pages, the customer's or supplier's own disclosures, government datasets with methodology), then independent specialist reporting, then everything else.
5. For each material gap try a primary route and a reasonable independent alternative where available; log actual attempts and stop after repetitive or inaccessible results. Do not treat an absent search hit as absence of the event.

## 2. Source ladder and independence
- Prefer the source authoritative for the specific claim: filings for reported accounts, a regulator for its decisions, a customer for its own purchasing, a data provider for its documented series.
- A company release, its newswire copy and articles repeating it are one origin. Count origins, not links. Show breadth across origins, not a raw source count.
- Competitor, customer and analyst interpretations are attributable CLAIMs; a counterparty's directly reported purchasing figure may be a FACT about its own records. Check market-size definitions and sponsor incentives.
- Independent corroboration is needed for disputed claims and consequential inferences. A single authoritative source can establish a directly reported fact.
- Read the strongest evidenced criticism and the company's response. Attribute opinions and allegations; an allegation is not a finding.

## 3. Tools and their limits (details in the skills)
- Use only tools actually available in your frontmatter/session. Search results and page summaries discover candidates; open the source before a material conclusion or exact quote. If no web tool is available, use public URLs from the library and document the coverage limit.
- Use browser text snapshots if available; inspect a rendered table when its text is ambiguous. Record a block or registration gate and move on. Do not register, log in, or bypass controls.
- Use cached documents and `agent_fetch.py` for SEC/Finviz. For other public sites, bounded `curl -sS -L -m 30 --max-redirs 3 --proto '=https' --proto-redir '=https'` to `work/downloads/` is allowed; save the command and final URL, then check content type, date and actual body before citing. Do not execute downloaded content.
- For PDFs, use available text extraction and visually check material scanned or ambiguous figures against the original. If visual verification is unavailable, mark the figure unverified.
- Record each retrieval: URL, retrieval time, the page's own "last updated" or publication date, units and geography. A page snapshot is a point in time, not a series.

## 4. Quality rules
- Tie every finding to a research question. Weight conclusions by evidence quality and materiality; the record may be asymmetric, so do not force balance. Say what each side gets right, what is unproven, and which facts would change the conclusion.
- Use the INFERENCE table (CONTRACT section 6) for material interpretations. Alternatives are hypotheses unless supported; label them.
- Do not use job ads as demand evidence, trading as motive evidence, or timing as proof of cause. A benchmark moving does not prove a company-specific effect: explain the company's actual exposure (contract lags, pass-through, hedging) or mark it UNKNOWN.
- A newly found route is **tested** only after opening the source and checking its relevant claim or figure, date, scope and units where relevant; mark limited checks partial and uninspected routes untested. This is source validation, not a demand for a second website: an authoritative primary document can support its own directly reported fact. Log the result under "New sources".
- Stop when new searches only return the same origins, when the questions are answered or shown unanswerable with the available public sources, or when your agent file's stop condition is met. Report unfinished work and its likely effect.
