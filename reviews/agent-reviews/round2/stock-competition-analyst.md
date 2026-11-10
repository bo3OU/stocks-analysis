Revised file: [stock-competition-analyst.md](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round2/agents/stock-competition-analyst.md). The original is unchanged. The revision is shorter: 689 words versus 698.

### Findings

1. **C01 HIGH — `agents/stock-competition-analyst.md:15`.** `NEEDS_PEER_FETCH` has no handler in `agents/ORCHESTRATION.md:41-43`; the agent also says `BLOCKED` while continuing a required-peer comparison. Use the handled `BLOCKED` handoff and withhold a complete table until rerun. Spec §4.
2. **C02 HIGH — `agents/stock-competition-analyst.md:14,21`.** Peer discovery uses the live Finviz industry in `identity.json`, although the cutoff section excludes historical use of live snapshots. Require evidence available by `AS_OF` for historical peer selection. Spec §§1–2.
3. **C03 MEDIUM — `agents/stock-competition-analyst.md:15,21`.** Logging caps does not resolve a missing material exhibit or failed current document; the fetch instruction covers only an “older filing.” The SNDK inventory shows six of twelve candidate exhibits downloaded for one 8-K. Fetch the identified document or mark the comparison blocked. Spec §§1, 3.
4. **C04 MEDIUM — `agents/stock-competition-analyst.md:16`.** A metric row allows one filing date and source URL, while growth and multiples can depend on several documents and observation dates. Preserve every input’s source, location and availability. Spec §1.
5. **C05 MEDIUM — `agents/stock-competition-analyst.md:17`.** Requiring a *filing* passage for every customer, supplier or JV tie excludes firsthand procurement disclosures and announcements allowed by Spec §3. Accept opened primary disclosures with their commercial context.
6. **C06 MEDIUM — `agents/stock-competition-analyst.md:11`.** Unknown security class stops business comparisons even when only class-dependent multiples are affected. Limit that block to the affected metrics. Spec §2.
7. **C07 MEDIUM — `agents/stock-competition-analyst.md:10`.** The required `company-data-fetch` skill says to run the fetcher, conflicting with `CONTRACT.md:28` and this agent’s no-fetch rule. Remove that skill reference. Spec §4.
8. **C08 MEDIUM — `agents/stock-competition-analyst.md:17`.** Industry-series work can duplicate the parallel market agent’s work. Reuse its dated findings when ready, then search remaining gaps. Spec §§4, E.

### Acceptance checks

- At an `AS_OF` before 2026-10-30, exclude SNDK’s 10-Q filed that day despite its 2026-10-02 period end.
- Use the filing’s 2026-10-02 period end, rather than Finviz’s normalized 2026-09-30 date.
- For a material SNDK 8-K exhibit among the six uncached candidates, fetch it or disclose the gap.
- If TSM is proposed as a peer, do not splice its TWD filing figures with Finviz’s USD conversions.
- Do not treat SNDK’s sampled −13.47% earnings reaction as proof of a moat change.

COUNTS: HIGH=2 MEDIUM=6 LOW=0  
CONVERGED: yes