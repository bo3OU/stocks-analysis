#!/bin/zsh
# Run fetch_company.py for several tickers one after another (sequential: shared SEC/Finviz rate limits).
# Usage: scripts/run_batch.sh MU TSM JPM OKLO
cd "$(dirname "$0")/.." || exit 1
mkdir -p research/_logs
for t in "$@"; do
  echo "=== $t $(date +%H:%M:%S)"
  /usr/bin/time -p .venv/bin/python -I scripts/fetch_company.py "$t" > "research/_logs/$t.log" 2>&1
  tail -3 "research/_logs/$t.log"
done
