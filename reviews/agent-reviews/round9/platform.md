## Round 9 findings

1. **R9-01 — HIGH — `scripts/common.py:121–125`; `scripts/agent_fetch.py:70–93`.** The public guard accepted `api-key`, `x-api-key`, and `x=1;token=...`; the SEC and Finviz routes also accepted caller-supplied secret-like query keys. Such values could be sent and logged. This conflicts with the no-secrets rule in spec §1. The revision normalizes query keys, rejects ambiguous separators and nested encoding, and applies the guard to all three routes.

2. **R9-02 — HIGH — `scripts/common.py:392–394`; `scripts/agent_fetch.py:98, 130–131, 141–143`.** A pre-existing symlink at the fixed `.tmp`, converted-text, or fetch-log path could redirect a script write outside the agent folder, contrary to spec §4. The revision uses exclusive temporary files, atomic replacement, and a no-follow log open.

3. **R9-03 — MEDIUM — `scripts/agent_fetch.py:39–41, 70–97`.** Early refusals appeared on stdout but were absent from `fetches.jsonl`, despite the script’s logging promise. That weakens the coverage record required by spec §§3–4. The revision records refusals after path validation without storing a potentially secret URL.

All seven requested revisions are under [revised/round9](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round9). The originals were not changed. I found no further handoff or rulebook correction in the shared documents.

**Verification:** Both revised scripts parse; credential-query cases pass; the SNDK sample anchors for the 600-share plan sale, 4,704,783 shares short, and −13.47% earnings-window return match. Acceptance checks for an agent run should also verify the 11,031 USD million reported revenue against the original 10-Q, distinguish the Form 4 sale from motive, keep short interest separate from daily short-sale volume, and avoid calling the earnings-window return causal. The full HTTP suite could not run because this workspace lacks `.venv` and `requests`.

COUNTS: HIGH=2 MEDIUM=1 LOW=0  
CONVERGED: yes