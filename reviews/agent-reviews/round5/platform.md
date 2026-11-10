## Round 5 findings

1. **P5-01 HIGH — `agents/CONTRACT.md:35`.** “None means zero or never happened” reverses the gap rule in spec §1, *Handle gaps honestly*. **Fix:** the revision says none of the gap terms implies zero or that an event never happened.
2. **P5-02 MEDIUM — `scripts/common.py:210`, `scripts/agent_fetch.py:110`.** Both use file modification time as a fallback retrieval time. That cannot establish availability at an exact `AS_OF` (spec §1, *Preserve dates*). **Fix:** record `unknown` when retrieval provenance is missing.
3. **P5-03 MEDIUM — `scripts/common.py:278`, `scripts/agent_fetch.py:126`.** A successful redirect records the requested URL but omits the URL that supplied the content, weakening source inspection (spec §1, *Read and identify the actual source*). **Fix:** record and return a redacted `final_url`.
4. **P5-04 MEDIUM — `agents/CONTRACT.md:47`.** The claim schema has no explicit availability timestamp for intraday cutoff checks, though `acceptanceDateTime` exists in the sampled filings index (spec §1, *Preserve dates*). **Fix:** add `available_at` when intraday eligibility matters.
5. **P5-05 MEDIUM — `agents/ORCHESTRATION.md:11,35`.** Phase 3 follows the filings reader, but `stock-positioning-analyst.md:14` still permits a parallel phase 2 run. That can lose the ownership handoff (spec §4, *Research organization and dependencies*). **Fix:** make phase 3 order and the current-run findings/claims handoff explicit.
6. **P5-06 MEDIUM — `agents/ORCHESTRATION.md:19`.** It assigns public bond trades to positioning, whose work list contains no bond-trade step; material credit evidence could go unsearched (spec §6, *Bonds and credit*). **Fix:** require a specific `FOCUS` brief and a supported result or logged gap.
7. **P5-07 LOW — `agents/SOURCE_LIBRARY.md:9`.** “Live snapshots” also describes the price-history export, obscuring the distinction between historical rows and live fields. **Fix:** clarify their separate limitations.

Revised copies of all seven reviewed files are in [revised/round5/agents/CONTRACT.md](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round5/agents/CONTRACT.md) and the adjacent `agents/` and `scripts/` paths. The revised Python compiled, and a local cache check confirmed unknown provenance stays unknown while known retrieval time and final URL are preserved. Network fetching was not tested because `requests` is unavailable here.

**Acceptance checks using SNDK samples:** verify the 11,031 USD million quarterly revenue against the filing period ending 2026-10-02 rather than Finviz’s 9/30 label; classify the 600-share Form 4 sale at 1158.26 as a sale without inferring motive; retain 4,704,783 shares short at the 2026-10-15 settlement while flagging the later blocked fetch; treat the −13.47% earnings reaction as a candidate return, not proven causation.

COUNTS: HIGH=1 MEDIUM=5 LOW=1
CONVERGED: yes