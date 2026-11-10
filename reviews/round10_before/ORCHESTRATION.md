# Orchestration guide (for the stock-deep-dive orchestrator and for the user)

`PROMPT_ORCHESTRATOR.md` governs the report. Pass absolute ROOT (this file's parent directory's parent) in every brief. The orchestrator alone fetches company/peer caches and writes the draft and final report; each agent writes only in `research/<TICKER>/agents/<agent>/`.

## Run order
| Phase | Who | Needs |
|---|---|---|
| 0 Scope | orchestrator | verify issuer identity (legal name, CIK, exchange symbol, share class/ADR, reporting currency/standard, fiscal year end) with cited evidence; choose relevant peers without padding, 4-7 questions, competing explanations and a source-family plan per question |
| 1 Fetch | orchestrator runs `ROOT/.venv/bin/python -I ROOT/scripts/fetch_company.py <TICKER> [--as-of "YYYY-MM-DD HH:MM"]` and each peer with the same flag, sequentially; the script prints `RESEARCH_DIR=<folder>`: use exactly that folder in every brief (the point-in-time cutoff is applied by the script, not by the agents) | use each normalized cache ticker (dots become hyphens) in briefs and paths; confirm CIK and other identity fields, `INVENTORY.md`, manifest, caps and gaps; fetch missing required records or mark a block before delegation |
| 2 Filings | `stock-filings-reader` alone | phase 1 |
| 3 Research, numbers and positioning, in parallel | `stock-financials-analyst`, `stock-positioning-analyst`, `stock-management-analyst`, `stock-market-analyst`, `stock-geopolitics-analyst`, `stock-competition-analyst` | pass the filings reader's exact current-run findings and claims pair in `PRIOR_FINDINGS` to each, after verifying that run's `AS_OF` and that both files are complete. No agent reads another agent's output opportunistically. If filings is blocked, pass `PRIOR_FINDINGS: filings reader BLOCKED: <reason>`; financials blocks, while the other five work from cache only when `FOCUS` explicitly authorizes that fallback and they state the coverage gap |
| 4 Valuation | `stock-valuation-analyst` | financials tables/calculation appendix, filings claims, competition peer table or stated gap, and positioning's dated price basis or gap |
| 5 Challenge | `stock-challenger` | developing thesis with claim IDs and all available findings |
| 6 Reconcile | `stock-reconciler` | completed claims/calculations and `report_draft.md` with material drivers and claim IDs; reopen original sources |
| 7 Report | orchestrator | all of the above; unresolved discrepancies stay visible |

Before phase 1, check `ROOT/.venv/bin/python` and imports of `requests`, `lxml` and `bs4`; use `scripts/README.md` setup if absent, or report `BLOCKED: environment` before delegation. Start research only after required caches are ready. Agents cannot run `fetch_company.py`. Tell competition in `FOCUS` to read prefetched peer caches and report `BLOCKED` for a missing required peer. SEC/Finviz fetches share one rate budget; do not retry persistent blocks or equate missing cache with missing evidence.

Assign material section 6 modules in `FOCUS`, with reasons for omitting others; owners and procedures are in `ROOT/agents/SPECIALIST_MODULES.md` (filings: insiders and 13D/G; positioning: price, short interest, options, 13F coverage, bond trades and terms; financials: debt terms and liquidity; valuation: bond yields; geopolitics: awards, imports, healthcare and product regulation; management: hiring; political disclosures are deferred). For material bond trades, explicitly brief positioning to seek a dated public trade source by bond identifier and report price convention, liquidity, seniority and call terms, or a logged `not obtained` gap; valuation computes any supported yield. Market leads products/customers; competition leads peers; challenger leads independent criticism. Record each section 6 module as used, not applicable or relevant but not obtained; repeated use of one filing is one origin.

## Brief template (send to every agent)
```
TICKER: <e.g. SNDK>
ROOT: <absolute project root>
AS_OF: <date and time with timezone, e.g. 2026-11-09 16:00 America/New_York>
RESEARCH_DIR: <folder printed by fetch_company.py>
QUESTIONS: 1) ... 2) ... (4-7 company-specific research questions)
COMPETING_EXPLANATIONS: <provisional list, including a plausible ordinary explanation>
ISSUER_IDENTITY: <legal issuer; CIK/local ID; exchange symbol and exchange; share class/ADR; reporting currency and accounting standard; fiscal year-end; source URL/location/date>
PEERS: <canonical cache ticker - one-line rationale>, ...        (competition and valuation agents)
THESIS: <leading explanation(s) and the claims it rests on>   (challenger only)
PRIOR_FINDINGS: <exact current-run paths to findings.md / claims.jsonl the agent may read>
FOCUS: <anything specific>
```
Read `ROOT/agents/<name>.md` and `CONTRACT.md`. Run positioning in phase 3; pass the filings reader pair or its explicit blocked status. Pass valuation exact current-run financials, filings, competition, product-market and positioning paths, distinguishing product from stock price. Before reconciliation write `RESEARCH_DIR/report_draft.md` with both sides' material drivers and claim IDs. Verify handoff files, issuer and AS_OF; a missing required handoff from a completed agent is `BLOCKED`, optional data a gap. The fetch script applies the cutoff; never give an as-of run a live folder.

## What the orchestrator reads
1. `INVENTORY.md`, then each agent's `findings.md` and relevant `claims.jsonl`.
2. `agents/stock-reconciler/reconciliation.md` and `.csv` before reporting; retain unresolved mismatches and unverified claims.
3. `search_log.md` and saved inputs to build the source register, coverage/gaps log, calculations and claim ledger. Cite originals beside material report facts; return new material assertions to the reconciler.

## Handling problems
- On `BLOCKED: ...`, fix the required input and rerun that agent; if unavailable, disclose the limitation.
- A rerun moves the old `findings.md` and `claims.jsonl` into `history/`. Never rerun an agent while its dependents are running: after any upstream rerun, stop and restart every affected downstream agent with the new verified pair.
- Do not average disagreements; ask the reconciler to check both sources.
- Audit actual coverage across spec section 3 families: reviewed, attempted unavailable, not applicable, not searched. Check IDs, locations, origins, dates/units, contrary evidence and supported bull/bear cases. No buy/sell/hold or single target price.
