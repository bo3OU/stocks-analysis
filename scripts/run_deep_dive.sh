#!/bin/zsh
# Two-stage deep-dive launcher: a fresh, small context for the report. All stages use Sonnet; the stock-* agents run on Haiku (their own frontmatter).
#   scripts/run_deep_dive.sh TICKER "Company name, EXCHANGE" [A|B|R|both] [extra instruction]
# Stage A (Sonnet orchestrator): scope, fetch, prepare, specialists (in two batches), valuation, challenger, reconciler; stops before the report.
# Stage B (Sonnet, fresh context): reads what is on disk and writes research/<TICKER>/report.md (full) and brief.md (STE style, 800 words max).
# Each stage writes its stream log (timestamped) to research/_logs/<TICKER>_stage<A|B>.jsonl; read it with scripts/cost_ledger.py report.
ROOT="${0:A:h:h}"
T="$1"; NAME="$2"; STAGE="${3:-both}"; EXTRA="$4"
[ -z "$T" ] && { echo "usage: $0 TICKER \"Company name, EXCHANGE\" [A|B|R|both] [extra]"; exit 2; }
cd "$ROOT" || exit 1
mkdir -p research/_logs
TOOLS="Agent Read Write Edit Grep Glob WebSearch WebFetch Bash($ROOT/.venv/bin/python *) Bash(.venv/bin/python *) Bash(pdftotext *) Bash(pdfinfo *) Bash(ls *) Bash(cd *) Bash(cat *) Bash(sed *) Bash(find *) Bash(grep *) Bash(head *) Bash(tail *) Bash(wc *) Bash(sort *) Bash(uniq *) Bash(cut *) Bash(tr *) Bash(awk *) Bash(jq *) Bash(diff *) Bash(mkdir *) Bash(mv *) Bash(cp *) Bash(date *) Bash(echo *) Bash(stat *) Bash(file *)"
run() { # model, budget, prompt, log
  claude --agent stock-deep-dive --model "$1" -p "$3" --permission-mode acceptEdits --allowedTools "$TOOLS" \
    --max-budget-usd "$2" --output-format stream-json --verbose | .venv/bin/python -I scripts/cost_ledger.py stamp > "$4"
}
if [ "$STAGE" = "A" ] || [ "$STAGE" = "both" ]; then
  run sonnet 20 "Follow agents/ORCHESTRATION.md.
Ticker: $T ($NAME). ROOT: $ROOT
Live run, no as-of cutoff: AS_OF is the current date and time in America/New_York; do not pass --as-of.
Keep it simple: about 4 research questions, at most 3 peers. Use the tool-call budgets in agents/CONTRACT.md. Run phase 3 in two batches (three specialists each) and save each batch's findings before the next.
STOP after phase 6 (reconciliation): do NOT write the final report; leave report_draft.md, the findings, claims and reconciliation on disk and print a 10-line status. $EXTRA" "research/_logs/${T}_stageA.jsonl"
fi
if [ "$STAGE" = "R" ]; then  # resume stage A after a usage limit or crash: reuse everything on disk
  run sonnet 20 "Follow agents/ORCHESTRATION.md.
Ticker: $T ($NAME). ROOT: $ROOT
RESUME of stage A: an earlier run was cut off. Reuse research/$T (scope.md, orchestrator/, prepared digest/ and tables/, and every agent output that has BOTH findings.md and claims.jsonl, verified with handoff.py check). Re-run fresh any agent that has no complete findings.md and claims.jsonl pair; ignore stray empty folders. Run the missing specialists in batches of three, save each batch with handoff.py save before the next, then valuation, challenger and reconciler. Use the tool-call budgets in agents/CONTRACT.md.
STOP after phase 6: do NOT write the final report; leave report_draft.md, findings, claims and reconciliation on disk and print a 10-line status. $EXTRA" "research/_logs/${T}_stageR.jsonl"
fi
if [ "$STAGE" = "B" ] || [ "$STAGE" = "both" ]; then
  run sonnet 8 "Follow agents/ORCHESTRATION.md.
Ticker: $T ($NAME). ROOT: $ROOT
Phase 7 only: phases 0-6 are complete in research/$T. Do not run any agent or fetch anything. Read scope.md, report_draft.md, each agents/*/findings.md, agents/stock-reconciler/reconciliation.md and the claims as needed, run handoff.py appendix, collect every agent work/PROMOTE.md into research/$T/promote_candidates.md, and write research/$T/report.md per your system prompt (unresolved discrepancies stay visible, no buy/sell/hold, no single target price).
Then write research/$T/brief.md for a reader who must decide and understand the story of the company: follow agents/STYLE_STE.md exactly (STE style, 800 words max, a claim ID on every sentence with a number, unknowns stated). Run scripts/ste_lint.py on it and fix the ERROR lines once. Nothing in the brief may be missing from report.md.
Finish by printing brief.md and listing the files. $EXTRA" "research/_logs/${T}_stageB.jsonl"
fi
