## Round 10 findings

- **R10-01 HIGH — `scripts/fetch_company.py:163`:** As-of manifest entries exposed paths to unfiltered SEC and Finviz files in `_cache`. The revised manifest retains retrieval status but removes those paths.
- **R10-02 HIGH — `scripts/fetch_company.py:83`:** Partial reruns could carry stale generated files into an as-of folder. The revision rejects as-of `--only` and clears generated files before a full rebuild.
- **R10-03 HIGH — `scripts/agent_fetch.py:76`:** A missing or linked `asof.json` could bypass cutoff enforcement; the live SEC ticker map was also allowed. The revision validates folder metadata and refuses that map.
- **R10-04 HIGH — `scripts/common.py:352`:** An approved SEC document URL could redirect to another SEC path without an as-of eligibility check. The revised fetch rejects a changed final document URL.
- **R10-05 MEDIUM — `scripts/asof.py:102`:** XBRL retained retrieval-time frames and descriptions and trusted a pre-cutoff `filed` date despite a known later acceptance. The revision removes those fields and uses the acceptance instant when known.
- **R10-06 MEDIUM — `scripts/asof.py:28`:** Ambiguous DST times and seconds could produce an unintended cutoff or collide with minute-based folder names. Both are now rejected.
- **R10-07 MEDIUM — `scripts/fetch_company.py:187`:** As-of identity contained current SEC profile fields. The revision omits them and directs historical identity checks to eligible filings.
- **R10-08 MEDIUM — `agents/ORCHESTRATION.md:9`:** Peer instructions could lead competition to a live `<PEER>` folder. The revised brief supplies exact peer directories and requires matching UTC cutoffs.
- **R10-09 MEDIUM — `agents/CONTRACT.md:39`:** “Everything” in the folder was described as cutoff-safe, including agent-gathered pages. The revision requires publication *and version* checks, including a time for same-day intraday evidence.
- **R10-10 MEDIUM — `scripts/asof.py:59`:** A fixed 16:05 close and assumed FINRA, Reg SHO and Treasury availability cannot establish every historical publication instant; half-day earnings reactions can be misclassified. These remain documented limits.
- **R10-11 MEDIUM — `agents/CONTRACT.md:1`:** The 1,390-word contract exceeded the 1,300-word budget. The revision is 1,292 words.

[Revised files](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round10) include every file under review plus the dependent as-of scripts, regression checks and README. Unfiltered JSON remains outside as-of folders; later split adjustments in Finviz prices cannot be reconstructed. Python compilation and isolated cutoff, rerun and manifest checks passed. Full SNDK regression could not run because this workspace has no `.venv` or `research/` data.

**SNDK acceptance checks:** At 2026-10-29 16:00 New York, exclude the 16:13 earnings 8-K and that day’s close; at 16:30, include both but exclude the 2026-10-30 10-Q; exclude the November 2 Form 4 sale of 600 shares; do not show the −13.47% earnings reaction before its October 30 reaction close.

COUNTS: HIGH=4 MEDIUM=7 LOW=0  
CONVERGED: no