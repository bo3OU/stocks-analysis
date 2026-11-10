## Round 7 findings

1. **P7-01 HIGH — `scripts/common.py:112,247`**. The public fetch checks DNS, then Requests resolves the host again; environment proxies can bypass that check. Pin the vetted address through the connection and disable proxies. This affects the public-information boundary in spec §1 and retrieval controls in §4.
2. **P7-02 MEDIUM — `scripts/common.py:247,321`**. Redirects use the first host’s rate-limit and 429 buckets. Key each hop to its actual host (spec §4).
3. **P7-03 MEDIUM — `scripts/agent_fetch.py:70,95`**. A public fetch reads `.env` and refuses to run without an SEC User-Agent. Require that setting only for SEC requests (spec §4).
4. **P7-04 MEDIUM — `agents/RESEARCH_PROTOCOL.md:19`, `scripts/agent_fetch.py:136`**. Agents are told to inspect content type, but the command omits it. Return and log `content_type` (spec §1, dates and source accuracy).
5. **P7-05 MEDIUM — `agents/RESEARCH_PROTOCOL.md:19`**. The management agent still names a nonexistent `curl` route at `agents/stock-management-analyst.md:16`. Explicitly supersede it with the guarded public fetch (spec §4).
6. **P7-06 MEDIUM — `agents/ORCHESTRATION.md:11`**. The filings-blocked fallback conflicts with the contract’s required-handoff gate. Pass an explicit blocked status and authorize cache-only work in `FOCUS` (spec §4).
7. **P7-07 MEDIUM — `agents/CONTRACT.md:29`**. Management depends on a filings-reader insider ledger, but no shared rule guarantees its path or fields. Require a linked `work/insider_ledger.csv` (spec §§4, 6).
8. **P7-08 MEDIUM — `agents/ORCHESTRATION.md:19`**. Asking positioning for a bond “yield method” blurs the assigned valuation calculation. Limit its handoff to trades and terms; valuation computes yields (spec §6).
9. **P7-09 MEDIUM — `scripts/common.py:281-289`**. An oversized response loses `final_url`; a stream error can escape without a structured result. Log both failures without saving a partial body (spec §§1, 4).
10. **P7-10 LOW — `scripts/agent_fetch.py:80`, `scripts/common.py:263`**. Malformed ports or redirects can raise `ValueError` instead of producing a refusal. Catch malformed URLs.

All seven reviewed files are at [revised/round7](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round7). `RULEBOOK_FILINGS.md` and `SOURCE_LIBRARY.md` needed no changes. Syntax and isolated DNS, redirect, rate-limit, size-cap, and stream-failure checks passed. The repository HTTP suite could not run because this workspace lacks `.venv`.

**SNDK acceptance checks:** preserve the 600-share Form 4 sale at 1,158.26 on 2026-11-02 as a plan-reported sale; distinguish 4,704,783 shares short at 2026-10-15 from daily short-sale volume; report the −13.47% earnings-window return without claiming causation.

COUNTS: HIGH=1 MEDIUM=8 LOW=1  
CONVERGED: yes