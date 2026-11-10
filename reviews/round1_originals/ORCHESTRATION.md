# Orchestration guide (for the stock-deep-dive orchestrator and for the user)

The orchestrator is the user's `stock-deep-dive` prompt (untouched). It scopes the work, calls the specialist agents below, reads their `findings.md`, thinks across them and writes the final report. Agents are LLMs; scripts are their deterministic tools. Each agent writes only to `research/<TICKER>/agents/<agent>/` so the user can see what each searched and found.

## Run order
| Phase | Who | Needs |
|---|---|---|
| 0 Scope | orchestrator | verifies issuer identity (legal name, CIK, exchange, share class or ADR ratio, reporting standard, fiscal year end); chooses 3-5 peers; writes 4-7 research questions and provisional competing explanations |
| 1 Fetch | script `scripts/fetch_company.py <TICKER>` (and `<PEER>` later, by the competition agent) | read `INVENTORY.md`; stop and fix identity problems or large gaps before spending tokens |
| 2 Read and research, in parallel | `stock-filings-reader`, `stock-management-analyst`, `stock-market-analyst`, `stock-geopolitics-analyst`, `stock-competition-analyst` | phase 1 |
| 3 Numbers | `stock-financials-analyst` (after the filings reader has finished, for debt, leases and share counts) | filings reader output |
| 4 Valuation | `stock-valuation-analyst` | financials output; competition peer table if available |
| 5 Challenge | `stock-challenger` | orchestrator's thesis plus all findings |
| 6 Reconcile | `stock-reconciler` | all claims; the draft report if one exists |
| 7 Report | orchestrator | all of the above; unresolved discrepancies stay visible |

Run agents in the same phase concurrently; the fetch script and `agent_fetch.py` share one cross-process rate budget.

## Brief template (send to every agent)
```
TICKER: <e.g. SNDK>
AS_OF: <date and time with timezone, e.g. 2026-11-09 16:00 America/New_York>
RESEARCH_DIR: /Users/ali/Workspace/personal/trading/fundamental-analyser/research/<TICKER>
QUESTIONS: 1) ... 2) ... (4-7 company-specific research questions)
COMPETING_EXPLANATIONS: <provisional list, including a plausible ordinary explanation>
PEERS: <ticker - one-line rationale>, ...        (competition and valuation agents)
THESIS: <leading explanation(s) and the claims it rests on>   (challenger only)
PRIOR_FINDINGS: <paths to findings.md / claims.jsonl the agent may read>
FOCUS: <anything specific>
```
Read agent definitions at `ROOT/agents/<name>.md`; shared rules in `ROOT/agents/CONTRACT.md`.

## What the orchestrator reads
1. `INVENTORY.md` (gaps and warnings), then each agent's `findings.md` (short by design).
2. `claims.jsonl` only to trace a conclusion to its source.
3. `reconciliation.md` before writing: unresolved mismatches must appear in the report.
4. `search_log.md` files tell the user what was searched and what each source returned.

## Handling problems
- An agent replying `BLOCKED: ...` means a required input is missing: fix it and rerun that agent only.
- A rerun moves the old `findings.md` and `claims.jsonl` into `history/`.
- If agents disagree, do not average: keep both with sources and ask the reconciler to check the figure.
- Agents never recommend buy/sell/hold or a target price, and neither does the final report.
