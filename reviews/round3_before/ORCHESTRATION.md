# Orchestration guide (for the stock-deep-dive orchestrator and for the user)

`PROMPT_ORCHESTRATOR.md` governs the orchestrator's report. Resolve ROOT to the directory containing this file's `agents/` parent and pass it in every brief; substitute absolute paths and ticker values in command examples. The orchestrator scopes, runs the deterministic company/peer fetches, calls agents, reconciles, then synthesizes. Each agent writes only to `research/<TICKER>/agents/<agent>/`; the orchestrator alone writes shared cache and final report.

## Run order
| Phase | Who | Needs |
|---|---|---|
| 0 Scope | orchestrator | verify issuer identity (legal name, CIK, exchange symbol, share class/ADR, reporting currency/standard, fiscal year end) with cited evidence; choose relevant peers without padding, 4-7 questions, competing explanations and a source-family plan per question |
| 1 Fetch | orchestrator runs `ROOT/.venv/bin/python -I ROOT/scripts/fetch_company.py <TICKER>` and peer tickers sequentially | use each normalized cache ticker (dots become hyphens) in briefs and paths; confirm CIK and other identity fields, `INVENTORY.md`, manifest, caps and gaps; fetch missing required records or mark a block before delegation |
| 2 Read and research, in parallel | `stock-filings-reader`, `stock-management-analyst`, `stock-market-analyst`, `stock-geopolitics-analyst`, `stock-competition-analyst` | phase 1 |
| 3 Numbers | `stock-financials-analyst` (after the filings reader has finished, for debt, leases and share counts) | filings reader output |
| 4 Valuation | `stock-valuation-analyst` | financials tables/calculation appendix and competition peer table or stated gap |
| 5 Challenge | `stock-challenger` | developing thesis with claim IDs and all available findings |
| 6 Reconcile | `stock-reconciler` | completed claims/calculations and `report_draft.md` with material drivers and claim IDs; reopen original sources |
| 7 Report | orchestrator | all of the above; unresolved discrepancies stay visible |

Concurrent research may start only after its required cache is ready. Agents cannot run `fetch_company.py` because it writes outside their folders; a conflicting step in an agent definition is superseded by `CONTRACT.md`. Tell the competition agent in `FOCUS` that peers are prefetched and it must only read their caches; it reports `BLOCKED` for a required missing peer cache. All SEC/Finviz fetches share the script's rate budget. Do not retry persistent blocks or claim missing cache is missing evidence.

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
Read agent definitions at `ROOT/agents/<name>.md`; `ROOT/agents/CONTRACT.md` supplies shared rules and conflict resolution. Before reconciliation, write `RESEARCH_DIR/report_draft.md` with the developing synthesis, material drivers on both sides and their claim IDs; pass exact current-run upstream paths and verify each finding's issuer and AS_OF. For each handoff, verify required files exist and report an unmet dependency as `BLOCKED`; missing optional data becomes a gap. Use exact AS_OF instant, including intraday SEC acceptance times and source publication availability. Do not use later live snapshots to recreate a historical view.

## What the orchestrator reads
1. `INVENTORY.md` (gaps and warnings), then each agent's `findings.md` (short by design).
2. `claims.jsonl` only to trace a conclusion to its source.
3. `agents/stock-reconciler/reconciliation.md` and `.csv` before writing; unresolved mismatches and unverified material claims stay visible.
4. `search_log.md` files tell the user what was searched and what each source returned. The orchestrator builds the final source register, coverage/gaps log, calculation appendices and material claim ledger from these files and the saved inputs; it cites originals beside material facts in the report. Any new material claim added after reconciliation goes back through the reconciler.

## Handling problems
- An agent replying `BLOCKED: ...` means a required input is missing: fix it and rerun that agent only. If a source remains unavailable, disclose the consequent limitation instead of silently treating the workstream as complete.
- A rerun moves the old `findings.md` and `claims.jsonl` into `history/`.
- If agents disagree, do not average: keep both with sources and ask the reconciler to check the figure.
- Audit actual coverage of filings, issuer communications, counterparties, peers/industry, independent criticism, governance/ownership and market data; distinguish reviewed, attempted unavailable, not applicable and not searched. Check material claim IDs, source locations, deduplicated origins, dates/units, contrary evidence and both supported bull/bear cases before synthesis. The final report has no buy/sell/hold call or single target price.
