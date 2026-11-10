Revised file: [stock-positioning-analyst.md](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round4/agents/stock-positioning-analyst.md).

### Findings in the original

| ID | Severity | Location | Evidence and fix |
|---|---|---|---|
| P1 | HIGH | `agents/stock-positioning-analyst.md:26` | It allowed historical rows to be cut by `AS_OF` without proving when they became public. SNDK’s FINRA row has a 2026-10-15 *settlement* date; that is not its publication date. Require both observation and availability checks (spec §1, “Preserve dates, units, and scope”; §5.F). |
| P2 | HIGH | `agents/stock-positioning-analyst.md:18` | `derived/earnings_events.csv` uses 8-K item 2.02 acceptance times, which can follow the release; it also omits foreign-issuer release routes. Verify actual release timing and treat the CSV as candidates (spec §5.F). |
| P3 | MEDIUM | `agents/stock-positioning-analyst.md:11,21` | The filings reader runs in parallel under `ORCHESTRATION.md` phase 2. “If present” could accept stale findings, while the fallback could claim net activity from parsed rows without the reader’s original-filing checks. Require an exact current-run handoff or disclose limited coverage (spec §4; §6). |
| P4 | MEDIUM | `agents/stock-positioning-analyst.md:14` | The benchmark instruction omitted required `agent_fetch.py` flags and output path and told the agent to download without checking cache first. Use the contract command and check cache and date coverage (spec §1; §4). |
| P5 | MEDIUM | `agents/stock-positioning-analyst.md:18` | Earnings reactions required a benchmark return but omitted the sector comparison required by spec §5.F. Add the same-window sector return or a gap. |
| P6 | MEDIUM | `agents/stock-positioning-analyst.md:22,28` | It required reporting Finviz’s target-price field, then said “No … target price.” Distinguish a quoted, unattributed aggregator field from the agent’s own target (spec §1; §5.F). |

### SNDK acceptance checks

- Report the seven available earnings candidates, including the **−13.47%** close-to-close move after the 2026-10-29 8-K, while separately verifying release timing.
- Report **4,704,783** shares short at 2026-10-15; distinguish FINRA’s days-to-cover field from a calculation using its **8,315,919** average daily volume.
- Identify the **600-share sale at $1,158.26** on 2026-11-02 as a Form 4 observation under a disclosed Rule 10b5-1 plan, without inferring motive.
- For an `AS_OF` before the cache’s November retrieval, exclude the options and screener snapshots rather than backdating them.

COUNTS: HIGH=2 MEDIUM=4 LOW=0  
CONVERGED: yes