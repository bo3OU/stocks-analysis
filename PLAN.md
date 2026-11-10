# Plan: stock deep-dive agent system

Status date: 2026-11-09. Spec: the user's research prompt (installed untouched as `~/.claude/agents/stock-deep-dive.md`). Everything below serves that prompt; nothing in it is edited.

## 1. Principles
1. **Script first.** Anything deterministic is a script (no tokens, reproducible, unit-testable). An LLM agent is used only where interpretation or discovery is unavoidable, and it reads script output, not raw websites.
2. **Tested sources only.** Each agent gets a source manifest: source, exact URL pattern or command, date tested, fallback, what to do when blocked. A source found at run time is logged as *untested* and cannot support a material conclusion until verified. Agents have room to think in interpretation, never in data acquisition.
3. **Evidence discipline from the prompt:** every claim carries a label (FACT / CLAIM / CALC / INFERENCE / UNKNOWN), a source ID, period, unit and location. Findings go to files; the orchestrator reads short summaries.
4. **Do not edit the user's prompt.** Extra guidance lives in skills, agent files and this folder.
5. **As-of cutoff and evidence ledger.** The prompt requires excluding anything published after the cutoff. Every derived row and claim links to an immutable source, publication/acceptance time, location, period, unit and transformation; a source family or calculation cannot be marked complete in the report until those fields and the reconciliation pass (see section 9).
6. **Cost control:** cached data, standalone briefs, small context per worker, strong models only for challenger, reconciler and orchestration.

## 2. Pipeline
```
Phase 0  Scope        orchestrator: identity check, 3-5 peers, 4-7 questions, competing explanations, coverage plan
Phase 1  Fetch        SCRIPT   fetch_company.py for the target and each peer           [done]
Phase 2  Analyze      SCRIPTS  rules/flags, XBRL notes extraction, financials, peers table, positioning summary
Phase 3  Read+Research LLM workers in parallel: filings reader, management, market, geopolitics, competition
Phase 4  Valuation    script computes scenarios from assumptions the LLM proposes
Phase 5  Challenge    LLM: independent search for disconfirming evidence, given the thesis + claim ledger
Phase 6  Reconcile    SCRIPT checks numbers vs sources, LLM reopens originals for failures
Phase 7  Report       script assembles appendices; orchestrator writes sections 1-7
```

## 3. Components: script part vs LLM part

| # | Component | Script part (deterministic) | LLM part | Model tier | Status |
|---|---|---|---|---|---|
| 0 | Orchestrator (`stock-deep-dive`) | runs the scripts, assembles appendices | scope, dispatch, synthesis, final report | strong | agent file exists; wiring not done |
| 1 | Fetcher | `fetch_company.py` (SEC, Finviz, FINRA, Treasury) | none | none | **done, tested on 7 inputs** |
| 2 | Filings reader | `rules.py`: rulebook flags from derived CSVs, index and XBRL; `notes_xbrl.py`: dimensional XBRL facts (geography, segments, debt maturities, leases, contract liabilities) | extract what XBRL lacks from the text (concentration, commitments, contingencies, subsequent events, risk-factor changes), quote + location; flags, no conclusions | mid | not started |
| 3 | Financials and valuation | `financials.py`: standardized annual/quarterly/TTM tables from Finviz + XBRL, margins, FCF under stated definitions, DSO/DIO/DPO, accruals, ROIC, SBC and dilution, runway scenarios, currency handling, sector adapters; `valuation.py`: scenario DCF and reverse-DCF grid from an assumptions file | propose assumptions with reasoning, interpret quality of earnings | mid | not started |
| 4 | Management credibility | `timeline.py` from 8-K item codes; `fetch_transcripts.py` (route tested on SNDK only); guidance pulled from release text | promise-vs-outcome table, Q&A and tone shifts, risk-factor changes, pay incentives | mid | not started; sources need testing on more tickers |
| 5a | Market and demand | external series fetch from a tested source library | research the product market: size definition, customers, pricing, cycle, substitutes | mid-strong | not started |
| 5b | Geopolitics and country exposure | revenue/production/supplier geography from filings (via 2), FX and macro series | export controls, tariffs, sanctions, regulation, concentration risk | mid-strong | not started |
| 5c | Competition | `peers.py`: run fetch for peers, comparison table (growth, margins, leverage, valuation) | share, moat, how the company positions itself vs evidence, attributed claims | mid-strong | not started |
| 6 | Positioning (optional, small) | `positioning.py`: short-interest trend, options snapshot summary, insider net activity, 13D/G changes, earnings reactions | none or a few lines | none | not started |
| 7 | Challenger | none | independent search for disconfirming evidence; strongest alternative | strong | not started |
| 8 | Reconciler | `reconcile.py`: extract numeric claims, check against XBRL, Finviz and filing text, check labels/units/dates | reopen originals for failures and judgment cases | strong | not started |

5a to 5c are one agent type with three briefs (same capability, different checklist).

## 4. Shared contracts (build first; everything depends on them)
- **Layout:** `research/<T>/findings/<agent>.md` (readable) and `research/<T>/claims/<agent>.jsonl` (machine-readable).
- **Claim ledger row:** `claim_id, agent, label, statement, value, unit, period, source_id, location, retrieved_at, confidence_reason`. Source IDs are manifest IDs; external sources are added with `register_source.py` (URL, retrieval time, origin, test status).
- **Agent file template:** job; inputs (file paths); source manifest (tested / untested); rules; output schema; where it may think; stop conditions; token budget.
- **Test cards:** per component, golden facts on SNDK (already verified by hand) plus a run on a second company with a different shape (bank, foreign filer, pre-revenue).

## 5. Build order with acceptance criteria
| Milestone | Deliverable | Accepted when |
|---|---|---|
| M0 | Fetch script | done: 19/19 SNDK facts, 7 inputs run |
| M0b | Fetch script hardening (findings of the second opinion, section 9) | duplicate `accessionNumber` header fixed; `--as-of` cutoff implemented and Finviz live snapshots flagged unusable in as-of mode; stale derived files removed on failed reruns; response/schema validation; `Retry-After` date format handled; cross-process rate lock; per-owner Form 4 rows and plan-adoption dates from footnotes; ADR/share-class/exchange identity fields; configurable caps (`--max-6k`); `verify_sndk.py` still 19/19 |
| M1 | Shared contracts and templates | schemas written, `register_source.py` works, one agent file template reviewed |
| M2 | `rules.py` + `notes_xbrl.py` (inline-XBRL facts with contexts and dimensions parsed from the filing; test the filing's FilingSummary/R pages as a shortcut) | every rule cites its SEC source and has unit tests on real filings (SNDK, MU, JPM, TSM); geography, debt and lease facts match the 10-Q on SNDK (Asia 7,216 of 11,031) |
| M3 | `financials.py` + `valuation.py` | reproduces SNDK TTM revenue 28,971 and Q1 figures; handles bank line items (JPM), TWD vs USD (TSM), zero revenue (OKLO) |
| M4 | Filings reader agent | on SNDK and MU, notes and flags match golden facts, no unsupported conclusions |
| M5 | Management agent | transcript route tested on 4 tickers (large, mid, small, ADR) with a fallback order; promise-vs-outcome table checked by hand on one company |
| M6 | Market, geopolitics and competition agents | source library seeded and tested; run on SNDK (memory) and on a company from another sector; new sources logged as untested |
| M7 | `positioning.py` | summary matches Finviz and FINRA figures |
| M8 | Challenger and reconciler | reconciler catches planted errors (wrong period, unit, restated figure); challenger finds a real counter-argument or says none exists |
| M9 | Orchestrator wiring and end-to-end dry run | full report on SNDK, then a second ticker; checked against the prompt's final quality list; token cost per phase measured |
| M10 | Iterate on cost and quality | targets set from M9 measurements |

## 6. Rulebook scope for `rules.py` (written from SEC sources, not from memory)
Section 16 reporting and 16(b) short-swing matching; Form 4 timeliness; Rule 10b5-1 plan disclosure and cooling-off; Form 144 versus Form 4 reconciliation; Schedule 13D/G thresholds and changes; 8-K item events (1.01, 2.02, 4.01, 4.02, 5.02, 3.02); XBRL red flags (receivables vs revenue growth, DSO, inventory days, accruals, restatements, going-concern and material-weakness language). Each rule outputs a flag row with inputs, the rule citation and the false-positive risks. Rules flag; they do not conclude. A detailed draft of 12 checks with thresholds and SEC citations is in `reviews/sol-gpt-6-sol-2026-11-09.md` (question 2). Treat it as a draft: each citation is opened and confirmed against the SEC page before the rule is coded and tested.

## 7. Open decisions
1. **Who orchestrates?** Whether a subagent such as `stock-deep-dive` can spawn workers is untested. If not, the main session orchestrates and `stock-deep-dive` is the single-agent fallback. Test early (cheap).
2. **Model tiers** per component (table above is a proposal).
3. **Skills installation:** skills in `skills.md` must be copied into `~/.claude/skills/` (user does this); then confirm subagents see them.
4. **First end-to-end ticker:** SNDK by default; second ticker from a different sector.
5. **Positioning agent:** keep as a small script, or drop.
6. **Second-opinion reviews with Codex** at milestones (rulebook, code): Codex runs on the ChatGPT-account login (plan limits, no API billing). `gpt-6-sol` and `gpt-5.6-sol` work; `gpt-6.1-sol` is rejected on that login. Reviews run on a clean copy of the project without `.env` or research data.

## 8. Known risks
- Aggregator figures (Finviz) differ from filings in unit, period or currency: reconciler and currency flags exist for this reason.
- Sources that block automation (many IR sites, webcast players): transcripts and audio may stay `[UNKNOWN]` for some companies.
- Discovery agents (5a to 5c) are the least deterministic: they need the source library and strict logging of untested sources, or cost and quality will drift.
- Rules from memory can be wrong (example: Section 16(b) is a profit-recovery rule, not a holding requirement): every rule needs an SEC citation and a test.
- Caps in the fetch script (8-K 60, 6-K 12, Form 4 400, 13D/G 60) can hide history: INVENTORY.md lists each cap hit.

## 9. Second opinion: gpt-6-sol review (2026-11-09)
Full answer: `reviews/sol-gpt-6-sol-2026-11-09.md`. Sol read the spec, the scripts and sample outputs, read-only. I checked its claims against our files before adopting them.

**Confirmed bugs and gaps in the fetch script (all go to M0b)**
- `filings_index.csv` writes `accessionNumber` twice in its header (verified).
- A failed or partial rerun can leave yesterday's derived CSVs in place, because files are only written when rows exist (verified in the code).
- `int(Retry-After)` fails if the header is an HTTP date (verified in the code); rate limiting is per process only, so parallel runs can exceed shared limits.
- **No research cutoff:** selection uses today's date, but the prompt requires an as-of date and exclusion of later publications. Finviz statements, options, news and the stats row are live snapshots and cannot be time-travelled; in as-of mode they must be flagged unusable.
- HTTP 200 and a CSV content type are treated as success; there is no schema or completeness validation.
- Caps (12 of 111 TSM 6-Ks, 6 exhibits per filing, `.txt`/`.xml` exhibits skipped) can omit the decisive document.
- Form 4 parsing collapses co-filers into one string and the 10b5-1 flag is filing-level; the plan adoption date lives only in footnote text (regex extraction needed); legacy 13D/G stay unparsed.
- Identity is not verified beyond CIK: exchange, share class, ADR ratio, reporting standard and subsidiary boundary need explicit fields (a per-ADR valuation could otherwise use ordinary-share counts).
- Earnings reaction keys off the 8-K acceptance time, not the release time (low priority; cross-check with the Finviz earnings calendar).

**Adopted design changes**
- Cutoff-aware evidence ledger and release gate (Principle 5): the single change Sol would make now.
- Notes extraction order: inline-XBRL facts with contexts and dimensions first, then bounded text/table parsing, LLM only for ambiguity. The Company Facts API cannot supply dimensional notes (consistent with our SanDisk test).
- Rulebook: 12 cited review checks (Section 16 applicability, Form 4/5 timeliness, 16(b) candidate pairs for domestic issuers only, 10b5-1 cooling-off, plan-disclosure consistency, Form 144, 13D/G, 8-K event queue, 4.01/4.02, working-capital divergence, going-concern and controls text). Thresholds for working-capital divergence (receivables growth 20 points above revenue growth plus DSO up 15 days; inventory and contract-liability variants) are investigative, not accounting rules, and must be labelled as ours.
- Foreign issuers: Sol cites foreign-insider Section 16 reporting beginning 2026-03-18 for directors and officers (10% holders alone excluded; 16(b) not applicable). Our TSM data agrees: its first Form 4 in the index is dated 2026-03-18. The 16(b) rule must therefore be issuer-type aware.
- Script/LLM split per agent (financials, management, market/geo/competition, challenger, reconciler) matches section 3 of this plan; the challenger and reconciler get scripted checklists and gates.

**Sol's point not solved by the fetch script**
- Calls, issuer communications, counterparties, competitors and independent criticism are outside the pipeline by design. The coverage gate in the evidence ledger prevents the report from claiming those families were reviewed unless an agent recorded them.

## 10. Agent build status (2026-11-10)
Ten specialist agents exist in `agents/` and are installed in `~/.claude/agents/`: `stock-filings-reader`, `stock-financials-analyst`, `stock-valuation-analyst`, `stock-management-analyst`, `stock-market-analyst`, `stock-geopolitics-analyst`, `stock-competition-analyst`, `stock-positioning-analyst` (added after the round-3 review found no owner for price history, earnings reactions, short interest and options), `stock-challenger`, `stock-reconciler`. Shared documents: `CONTRACT.md`, `RESEARCH_PROTOCOL.md`, `RULEBOOK_FILINGS.md`, `SOURCE_LIBRARY.md`, `SPECIALIST_MODULES.md`, `ORCHESTRATION.md`. Tool: `scripts/agent_fetch.py` (sec, finviz, public). Not yet run on a real company.

Sol (gpt-6-sol) review records are in `reviews/agent-reviews/round1` to `round9`. HIGH / MEDIUM findings in the version reviewed:

| Component | R1 | R2 | R3 | later rounds |
|---|---|---|---|---|
| filings reader | 6 / 4 | 3 / 4 | 0 / 5 | R4 0 / 2 |
| financials | 4 / 4 | 2 / 5 | 0 / 2 | R4 0 / 0 |
| valuation | 6 / 1 | 2 / 3 | 0 / 4 | R5 0 / 2 |
| management | 2 / 6 | 1 / 5 | 0 / 3 | edited after cross-review |
| market | 1 / 4 | 1 / 2 | 1 / 1 | R4 0 / 1 |
| geopolitics | 2 / 5 | 0 / 6 | 0 / 4 | edited after cross-review |
| competition | 2 / 6 | 2 / 6 | 1 / 3 | R4 0 / 1 |
| positioning (new) | | | | R4 2 / 4, R5 0 / 4, R6 0 / 2 |
| challenger | 2 / 4 | 1 / 3 | 0 / 2 | R4 0 / 0 |
| reconciler | 4 / 6 | 1 / 5 | 1 / 2 | R4 0 / 4 |
| shared documents and scripts | 7 / 8 | 4 / 8 | 0 / 3 | R4 0 / 4, R5 1 / 5, R6 1 / 2, R7 1 / 8, R8 2 / 1, R9 2 / 1 |
| cross-agent review (all ten together) | | | | R6 1 / 6, R7 0 / 4, **R8 0 / 0** |

Reading the table: every agent file reached 0 HIGH. The cross-agent review (contradictions, ownership, handoffs, parallel-run risks) found real problems in R6 and R7, all fixed, and was clean in R8. The scripts kept yielding hardening items against increasingly adversarial scenarios (the `public` fetch kind added in R6 was new attack surface); I stopped after R9 and adopted its fixes. Agent files edited after their last Sol pass: management, market, geopolitics, competition, filings reader, valuation (small ownership and handoff fixes found by the cross-agent review; the final cross-agent pass R8 read them).
Local tests: `scripts/test_http_guards.py` (55 checks), `scripts/verify_sndk.py` (19 SNDK facts), seven tickers fetched.

Still open: `fetch_company.py` has no `--as-of` cutoff (agents are told how to apply it), caps on 6-Ks and exhibits, per-owner Form 4 rows, identity fields (ADR ratio, share class), and a first end-to-end run of the agents on SNDK.

## 11. As-of cutoff moved into the script (2026-11-10)
`fetch_company.py --as-of "YYYY-MM-DD HH:MM"` builds a point-in-time folder (`research/<TICKER>_asof_<stamp>/`) and `agent_fetch.py` enforces the same cutoff there; the agents no longer apply cutoffs to cache data (they only date-check sources they gather themselves). Rules, tests and limits: `scripts/README.md` ("Point-in-time (as-of) runs"), `scripts/verify_asof.py` (66 checks). Known limits: Finviz prices are split-adjusted as of retrieval; short-interest publication lag (14 days) is an unverified assumption; Finviz statements, options, news and consensus are unavailable at a past cutoff; identity fields are current. Political disclosures: deferred, an Unusual Whales subscription is planned.

## 12. State at end of session (2026-11-10)
As-of is done in scripts (`--as-of` + mandatory `--tz`, `folders_match.py`, `agent_fetch.py` enforcement; `verify_asof.py` 82 checks, `verify_sndk.py` 19, `test_http_guards.py` all passing). Sol review of this change: round 10 (platform 4/7, crosscheck 3/1) fully adopted; round 11 started: crosscheck returned 2 HIGH / 2 MEDIUM and the platform result was still pending, BOTH UNREAD and UNAPPLIED (see `reviews/agent-reviews/round11/` or the Codex job JSONs). Next: read round 11, apply, run round 12 (third iteration), then wire the orchestrator and do the SNDK dry run.
Round 11 cross-agent findings (2 HIGH / 2 MEDIUM) applied 2026-11-10: an as-of rebuild archives `agents/` and `report_draft.md` into `stale_before_rebuild_<UTC>/`; protocol fetch example uses the folder name; `folders_match.py` accepts a target-only run; `fetch_company.py --annual/--interim/--index-years` give agents a scripted way to request longer history. Tests pass (verify_asof 82, verify_sndk 19). Round 12 (third Sol iteration) has NOT been run.
