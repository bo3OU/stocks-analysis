# Research protocol (management, market, geopolitics, competition, challenger)

Read `CONTRACT.md` first. This file governs research beyond the cache.

## Search order

1. Read `ROOT/agents/SOURCE_LIBRARY.md`; prefer relevant tested routes, but recheck dated status, terms and scope. Check `INVENTORY.md`, exact `PRIOR_FINDINGS` and cached originals before searching.
2. Map each assigned question and material gap to a source family. Prefer the authority for the claim: filings for accounts, regulators for decisions, counterparties for their own actions, documented data providers for their series. A release and its mirrors share one origin. Count origins, not links.
3. For a material gap, attempt a primary route and a reasonable independent alternative where available. Read the strongest evidenced criticism and the company's response. Attribute allegations and interested interpretations; a counterparty's directly reported own figure can be FACT. A single authoritative document can support a directly reported fact; disputed claims and consequential inferences require independent corroboration.
4. Log actual attempts and coverage. Stop when questions are answered, public routes are unavailable, searches repeat origins, or the agent's stop condition holds. No search hit does not prove absence.

## Tools

Use only tools available in your frontmatter/session. Search results and page summaries find candidates; open originals before material conclusions or quotes. If no web tool exists, use public library URLs and disclose the limit. Inspect rendered tables when text is ambiguous; visually verify scanned or ambiguous PDF figures or mark them unverified.

Use cached SEC/Finviz material and `agent_fetch.py` as specified in `CONTRACT.md`. For other public sites, a bounded `curl -sS -L -m 30 --max-redirs 3 --proto '=https' --proto-redir '=https'` to `work/downloads/` is allowed. Save command and final URL; inspect content type, date and body before citing; never execute downloaded content. Record retrieval time, publication/last-updated date, units, geography and coverage. A live page is a snapshot, not a historical series. Log registration/paywall blocks and move on.

## Interpretation

Tie findings to questions and weigh evidence by quality and materiality. Apply the same standard to supported bull and bear explanations; do not force equal space or likelihood. For material INFERENCEs use the contract's table; unsupported alternatives are hypotheses or UNKNOWN. Separate a benchmark from the issuer's realized exposure: show contract lags, pass-through and hedging when disclosed, or mark the effect UNKNOWN. Check market-size definitions and sponsor incentives. Do not treat jobs, trades or timing as proof of demand, motive or cause.

New routes are tested only after opening and checking the relevant claim/figure, date, scope and units; limited checks are partial, uninspected routes untested. Record them under `search_log.md` “New sources.” Report unfinished work and its likely effect.
