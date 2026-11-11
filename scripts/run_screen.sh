#!/bin/zsh
# Screen mode: a 10-minute look at a company. Scripts fetch and prepare; ONE Sonnet call writes brief.md from the prepared files.
#   scripts/run_screen.sh TICKER "Company name, EXCHANGE" [extra instruction]
# No specialist agents, no web research. Cost target: about $1-2 and 6-12 minutes. Use run_deep_dive.sh when a company is worth the depth.
ROOT="${0:A:h:h}"
T="$1"; NAME="$2"; EXTRA="$3"
[ -z "$T" ] && { echo "usage: $0 TICKER \"Company name, EXCHANGE\" [extra]"; exit 2; }
cd "$ROOT" || exit 1
mkdir -p research/_logs
t0=$(date +%s)
echo "[1/3] fetch (script)"
.venv/bin/python -I scripts/fetch_company.py "$T" > "research/_logs/${T}_screen_fetch.log" 2>&1 || echo "  fetch reported errors; continuing (see research/_logs/${T}_screen_fetch.log)"
RD=$(grep -o 'RESEARCH_DIR=.*' "research/_logs/${T}_screen_fetch.log" | tail -1 | cut -d= -f2-)
F=$(basename "${RD:-$ROOT/research/$T}")
[ -f "research/$F/identity.json" ] || { echo "fetch failed: no research/$F/identity.json"; exit 1; }
echo "[2/3] prepare (script)"
.venv/bin/python -I scripts/prepare_company.py "$F" || echo "  some prepare steps failed: the brief must list them as gaps"
echo "[3/3] brief (one Sonnet call)"
TOOLS="Read Write Edit Grep Glob Bash($ROOT/.venv/bin/python *) Bash(.venv/bin/python *) Bash(ls *) Bash(cd *) Bash(cat *) Bash(sed *) Bash(grep *) Bash(head *) Bash(tail *) Bash(wc *) Bash(cut *)"
PROMPT="SCREEN MODE. Follow agents/ORCHESTRATION.md only for paths and tools. Do not start any specialist agent. Do not use the web. Ticker: $T ($NAME). ROOT: $ROOT. RESEARCH_DIR: research/$F. Live data, no as-of cutoff.
Goal: a reader must be able to decide whether this company deserves a deep dive and know its story, in 800 words or fewer.
Read in this order and nothing else unless needed: INVENTORY.md, identity.json (check that name, exchange, currency and share class match '$NAME'; state any mismatch), digest/digest.md, tables/financial_summary.md, tables/obligations_xbrl.md, tables/offerings.csv (newest rows), tables/catalysts.md, digest/insider_summary.md, tables/positioning.md, tables/proxy_tables.md (first rows). Open a passage only with ROOT/.venv/bin/python -I ROOT/scripts/read_section.py, at most 10 times, for the most material items (financing terms, going-concern or weakness wording, the newest 8-K items, the business description). Stay within about 25 tool calls.
Write research/$F/brief.md exactly in the structure and style of agents/STYLE_STE.md. In screen mode there are no claim IDs: end every sentence with a number with a source in brackets, [src: path] or [src: path:line], using the file you read (path relative to research/$F). Never state a number you did not read in a file.
Add a final section 'Not covered in screen mode' that lists, each as Unknown with one reason: management record and incentives, competition, market demand, geopolitics and regulation, valuation, short-interest and options detail beyond tables/positioning.md. State any failed prepare step or missing file as a gap. No buy, sell or hold call. No single target price.
Then run ROOT/.venv/bin/python -I ROOT/scripts/ste_lint.py $F and fix the ERROR lines once. Print the final brief. $EXTRA"
claude --agent stock-deep-dive --model sonnet -p "$PROMPT" --permission-mode acceptEdits --allowedTools "$TOOLS" \
  --max-budget-usd 3 --output-format stream-json --verbose | .venv/bin/python -I scripts/cost_ledger.py stamp > "research/_logs/${T}_screen.jsonl"
echo "done in $(( $(date +%s) - t0 )) s. Brief: research/$F/brief.md. Cost: .venv/bin/python -I scripts/cost_ledger.py report research/_logs/${T}_screen.jsonl"
