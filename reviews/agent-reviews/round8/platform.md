## Findings

1. **P8-01 HIGH — `scripts/common.py:126`, `scripts/agent_fetch.py:78`.** The `public` route accepted SEC and Finviz hosts, bypassing their dedicated request controls. This conflicts with the shared SEC User-Agent and rate-limit requirements in spec §4. **Fix:** reject those hosts on the public route, including redirects.

2. **P8-02 HIGH — `scripts/common.py:114`, `scripts/agent_fetch.py:142`.** A public URL containing `?api_key=...` was accepted and logged with its value; the redactor covered only the configured Finviz token. **Fix:** reject common credential query keys before fetching or logging, on every redirect hop.

3. **P8-03 MEDIUM — `agents/ORCHESTRATION.md:9`, `agents/CONTRACT.md:3`.** Every prescribed command needs `.venv`, which is absent in this checkout; the available `python3` also lacks `requests`. Research could fail after delegation. **Fix:** check the environment before phase 1 and report `BLOCKED: environment` if setup cannot be completed.

All seven copies are in [revised/round8](</private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round8>). `RULEBOOK_FILINGS.md` and `SOURCE_LIBRARY.md` needed no changes. Six focused guard checks passed; the full guard suite could not start without the project environment.

**SNDK acceptance checks:** verify the 600-share Form 4 sale at 1158.26 and attribute its plan footnote without inferring motive; report 4,704,783 shares short at the 2026-10-15 settlement date without treating the blocked later file as zero; describe the −13.47% earnings-window move without asserting cause; disclose that the cache contains only two annual reports.

COUNTS: HIGH=2 MEDIUM=1 LOW=0  
CONVERGED: yes