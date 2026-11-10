## Findings

1. **F01 HIGH — `agents/stock-filings-reader.md:18`.** The cutoff instruction covers filings but not XBRL `filed` dates or derived ownership rows. A historical run could use later evidence. **Fix:** filter each source by when it became available. Spec §1, “Preserve dates, units, and scope.”

2. **F02 HIGH — `agents/stock-filings-reader.md:21–24`.** The job centers on the latest annual and interim reports. The spec calls for up to three annuals and eight interim periods where available, including amendments and restatements. SNDK’s inventory has only two annuals and six 10-Qs; that limit must be reported. **Fix:** build and disclose a dated coverage queue. Spec §3, “Issuer filings.”

3. **F03 HIGH — `agents/stock-filings-reader.md:17,25`.** The inputs and event timeline assume 8-K text and item codes. Foreign issuers use 20-F/40-F and 6-K; the fetcher caps 6-Ks and derives no item-coded earnings events for them. **Fix:** add a foreign-issuer path and state its coverage. Spec §2, item 2.

4. **F04 HIGH — `agents/stock-filings-reader.md:25`.** “Open and summarize the exhibits” assumes complete cache coverage. `fetch_company.py` fetches at most six candidate exhibits per filing and does not select exhibits for 3.02/5.02 by item code; SNDK’s inventory records a capped filing. **Fix:** inspect each accession index, fetch material omissions, and disclose what remains missing. Spec §1, “Handle gaps honestly.”

5. **F05 HIGH — `agents/stock-filings-reader.md:26,33`.** “Apply rules exactly” can turn the rulebook’s explicitly unverified S16-C and E8K-A legal descriptions into asserted law. **Fix:** verify primary rule text before stating it as fact; otherwise report uncertainty. Spec §1, “Read and identify the actual source.”

6. **F06 HIGH — `agents/stock-filings-reader.md:26`.** A filing-level `rule_10b5_1` checkbox and a footnote do not necessarily establish the plan for every parsed transaction or a modification date. The requested cooling-off flag can therefore be false. **Fix:** inspect the raw Form 4 and required dates; mark an indeterminate check UNKNOWN. Spec §1, “Distinguish what is known from what is inferred.”

7. **F07 MEDIUM — `agents/stock-filings-reader.md:26`.** “Net open-market buying and selling” leaves grouping and eligible rows undefined. The parser includes derivatives, grants and tax withholding alongside P/S trades. **Fix:** specify person, security, period and P/S non-derivative filters, and save the calculation. Spec §5F.

8. **F08 MEDIUM — `agents/stock-filings-reader.md:17`.** Some primary ownership XML and exhibits have no `text/*.txt` version; the fetcher also keeps raw accession files. **Fix:** check cached raw files and `index.json` before fetching or declaring a gap. Spec §4, shared-cache requirement.

9. **F09 MEDIUM — `agents/stock-filings-reader.md:26`.** Name-only Form 144 matching and a holder list can misidentify sales or double-count joint 13D/G reporters. **Fix:** match within stated person, class, date and filing coverage; keep joint reporters distinct. Spec §5F.

10. **F10 MEDIUM — `agents/stock-filings-reader.md:30,40`.** Calling a whole 10-K “audited” overstates the scope of the audit, and the handoff does not identify which debt and share facts financials needs. **Fix:** qualify audit status per figure and surface those facts in `findings.md`. Spec §1, evidence labels; §4, dependencies.

Revised file: [revised/round1/agents/stock-filings-reader.md](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round1/agents/stock-filings-reader.md). The original was not changed.

## Acceptance checks

- SNDK coverage says **two annual reports and six 10-Qs**, matching `SNDK_INVENTORY.md`.
- The quarter ended 2026-10-02 reports **$11,031 million revenue**, with filing location, period and scale; `verify_sndk.py` identifies the source text.
- At an AS_OF before 2026-11-03, the **600-share Form 4 sale dated 2026-11-02** is excluded because it was filed on 2026-11-03.
- The 2026-11-06 13G/A is excluded from a 2026-11-05 cutoff, despite its earlier event date.
- The **−13.47%** post-earnings close-to-close move is never stated as caused by the filing.

COUNTS: HIGH=6 MEDIUM=4 LOW=0  
CONVERGED: yes

Codex session ID: 01a1bd7f-ba08-7061-ad66-c8bd4cad136a
Resume in Codex: codex resume 01a1bd7f-ba08-7061-ad66-c8bd4cad136a
