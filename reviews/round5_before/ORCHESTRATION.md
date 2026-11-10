# Orchestration guide (for the stock-deep-dive orchestrator and for the user)

`PROMPT_ORCHESTRATOR.md` governs the report. Pass absolute ROOT (this file's parent directory's parent) in every brief. The orchestrator alone fetches company/peer caches and writes the draft and final report; each agent writes only in `research/<TICKER>/agents/<agent>/`.

## Run order
| Phase | Who | Needs |
|---|---|---|
| 0 Scope | orchestrator | verify issuer identity (legal name, CIK, exchange symbol, share class/ADR, reporting currency/standard, fiscal year end) with cited evidence; choose relevant peers without padding, 4-7 questions, competing explanations and a source-family plan per question |
| 1 Fetch | orchestrator runs `ROOT/.venv/bin/python -I ROOT/scripts/fetch_company.py <TICKER>` and peer tickers sequentially | use each normalized cache ticker (dots become hyphens) in briefs and paths; confirm CIK and other identity fields, `INVENTORY.md`, manifest, caps and gaps; fetch missing required records or mark a block before delegation |
| 2 Read and research, in parallel | `stock-filings-reader`, `stock-management-analyst`, `stock-market-analyst`, `stock-geopolitics-analyst`, `stock-competition-analyst` | phase 1 |
| 3 Numbers and positioning, in parallel | `stock-financials-analyst`, `stock-positioning-analyst` | filings reader findings and claims; if filings is blocked, position's fallback checks issuer-matched records and states the gap |
| 4 Valuation | `stock-valuation-analyst` | financials tables/calculation appendix, competition peer table or stated gap, and positioning's dated price basis or gap |
| 5 Challenge | `stock-challenger` | developing thesis with claim IDs and all available findings |
| 6 Reconcile | `stock-reconciler` | completed claims/calculations and `report_draft.md` with material drivers and claim IDs; reopen original sources |
| 7 Report | orchestrator | all of the above; unresolved discrepancies stay visible |

Start research only after required caches are ready. Agents cannot run `fetch_company.py`. Tell competition in `FOCUS` to read prefetched peer caches and report `BLOCKED` for a missing required peer. SEC/Finviz fetches share one rate budget; do not retry persistent blocks or equate missing cache with missing evidence.

Assign material section 6 modules in `FOCUS`, with reasons for omitting others: filings leads insiders/13D/G; positioning leads price, short interest, options, institutional coverage and public bond trades, summarizing filings flags; financials leads debt terms/liquidity; valuation leads bond-price implications; geopolitics leads awards, imports and product regulation; management leads hiring and material political disclosures. Market leads products/customers; competition leads peers; challenger leads independent criticism. Mark inaccessible material modules `not obtained`; repeated use of one filing is one origin.

## Brief template (send to every agent)
```
TICKER: <e.g. SNDK>
ROOT: <absolute project root>
AS_OF: <date and time with timezone, e.g. 2026-11-09 16:00 America/New_York>
RESEARCH_DIR: <ROOT>/research/<TICKER>
QUESTIONS: 1) ... 2) ... (4-7 company-specific research questions)
COMPETING_EXPLANATIONS: <provisional list, including a plausible ordinary explanation>
ISSUER_IDENTITY: <legal issuer; CIK/local ID; exchange symbol and exchange; share class/ADR; reporting currency and accounting standard; fiscal year-end; source URL/location/date>
PEERS: <canonical cache ticker - one-line rationale>, ...        (competition and valuation agents)
THESIS: <leading explanation(s) and the claims it rests on>   (challenger only)
PRIOR_FINDINGS: <exact current-run paths to findings.md / claims.jsonl the agent may read>
FOCUS: <anything specific>
```
Read `ROOT/agents/<name>.md` and `CONTRACT.md`. Pass valuation exact current-run financials, filings, competition, product-market and positioning paths, distinguishing product from stock price. Before reconciliation write `RESEARCH_DIR/report_draft.md` with both sides' material drivers and claim IDs. Verify handoff files, issuer and AS_OF; a missing required handoff is `BLOCKED`, optional data a gap. Enforce intraday publication/SEC acceptance; never use later live snapshots to recreate history.

## What the orchestrator reads
1. `INVENTORY.md`, then each agent's `findings.md` and relevant `claims.jsonl`.
2. `agents/stock-reconciler/reconciliation.md` and `.csv` before reporting; retain unresolved mismatches and unverified claims.
3. `search_log.md` and saved inputs to build the source register, coverage/gaps log, calculations and claim ledger. Cite originals beside material report facts; return new material assertions to the reconciler.

## Handling problems
- On `BLOCKED: ...`, fix the required input and rerun that agent; if unavailable, disclose the limitation.
- A rerun moves the old `findings.md` and `claims.jsonl` into `history/`.
- Do not average disagreements; ask the reconciler to check both sources.
- Audit actual coverage across spec section 3 families: reviewed, attempted unavailable, not applicable, not searched. Check IDs, locations, origins, dates/units, contrary evidence and supported bull/bear cases. No buy/sell/hold or single target price.
