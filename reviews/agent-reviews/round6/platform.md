## Round 6 findings

| ID | Severity | Location and evidence | Fix |
|---|---|---|---|
| P6-01 | HIGH | `agents/CONTRACT.md:9` says to flag unresolved identity, but does not clearly block analysis. The SNDK cache lacks share-class and accounting-standard fields, so an agent could proceed without verifying them. This conflicts with spec §2.1 and §1.55. | Require `BLOCKED` for any unverified or conflicting required identity field. |
| P6-02 | MEDIUM | `agents/CONTRACT.md:47` leaves live-source retrieval and intraday availability timestamps under “add when applicable,” weakening the claim ledger’s cutoff audit. SNDK’s 2026-10-29 earnings event has a 16:13 acceptance time; the date alone is insufficient. Spec §1.51–53. | Explicitly require retrieval time for live sources and first-public time or `unknown` when intraday eligibility matters. |
| P6-03 | MEDIUM | `scripts/common.py:270–272,302–303` returns no `final_url` on failed responses, although `agent_fetch.py:125–132` exposes that field and the contract tells agents to inspect it. Redirected blocks therefore lose the endpoint needed to explain the attempt. Spec §1.51 and §4. | Preserve the final attempted URL in failed results and the manifest. |
| P6-04 | LOW | `agents/CONTRACT.md:43` does not name the file for “New sources”; `RESEARCH_PROTOCOL.md:22` names `search_log.md`. | Name `search_log.md` in the contract. |

All seven reviewed files have copies under [revised/round6](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round6). Changes are in [CONTRACT.md](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round6/agents/CONTRACT.md) and [common.py](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round6/scripts/common.py); the other five copies needed no change. Originals were not edited.

**Acceptance checks using SNDK:** Verify filing revenue of 11,031 USD millions for the quarter ended 2026-10-02; classify the 2026-11-02 Form 4 sale of 600 shares at 1158.26 as a reported plan transaction without inferring motive; keep 4,704,783 shares of 2026-10-15 short interest separate from daily short-sale volume; and report the −13.47% post-earnings return without asserting causation. The revised scripts passed syntax parsing and mocked failed-response URL checks; live fetches were not run.

COUNTS: HIGH=1 MEDIUM=2 LOW=1
CONVERGED: yes