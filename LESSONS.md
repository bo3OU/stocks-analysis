# What worked and what did not (updated as runs happen)

## Platform facts
- Subagents cannot write report-style files such as `findings.md` (Claude Code refuses). They return the text; the orchestrator saves it with `handoff.py save`.
- Headless runs cannot ask permission. The allowlist must cover `cd`, `cat`, `sed`, `find` and the venv python; shell variables and compound commands are denied.
- Start the orchestrator as the main session. In one run it delegated everything to a nested copy of itself: it lost control and paid twice.
- A usage limit kills in-flight agents, and agents write their files only at the end. Run the specialists in batches of three and save after each batch.
- A long chat session is the biggest cost (VKTX run: chat about 413K tokens per request, 258M cache-read tokens; the whole VKTX pipeline used about 74M). Run pipelines from a terminal or a fresh session.

## Cost facts (VKTX, API-price estimates)
- Old setup about $36 useful (Opus 45%, Sonnet 49%, Haiku 6%), about two 5-hour windows including waste.
- The filings reader on Haiku cost $1.9 against $4.7 on Sonnet but missed material facts (a $316.25M raise, the lock-up). The coverage check finds such gaps.
- Web-research agents used 150+ tool calls each until a call budget (about 50) and batching were added; then about 35.
- Turns, not filings, drive cost: each turn re-reads the whole context, and each agent writes 40 to 70 claims one tool call at a time.

## What the scripts changed
- Digest, insider ledger, tables, offerings, catalysts, proxy rows, positioning, peers, benchmark and runway replaced most of the reading and the hand-built tables.
- `verify_claims.py` and `audit_claims.py` found real defects (a claim cycle, claims citing nothing). Claim-format errors got worse on Haiku (100 of 373); a claim draft generator is the planned fix.
- `coverage_check.py` found the missing offering filing and lock-up in the new VKTX run.

## Modes
- `scripts/run_screen.sh`: scripts plus one Sonnet call, about 10 minutes, no specialists. Untested end to end.
- `scripts/run_deep_dive.sh`: two stages on Sonnet, specialists on Haiku, in batches. Untested end to end on the new settings (first test: ZTS).

## Open items
- Claim draft generator (script builds schema-correct claims with line citations from the tables).
- Sol review of `coverage_check.py`, `cost_ledger.py`, `ste_lint.py`, the launchers.
- Decide whether Haiku is enough for the challenger and reconciler.
