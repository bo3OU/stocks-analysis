## Round 1 findings

Locations refer to [agents/stock-geopolitics-analyst.md](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/agents/stock-geopolitics-analyst.md).

| ID | Severity | Location | Evidence and fix |
|---|---|---|---|
| GEO-01 | HIGH | `agents/stock-geopolitics-analyst.md:15` | The exposure list does not distinguish reported sales geography from customer location, destination, supplier domicile, or production site. These can describe different risks. Spec §1, “Preserve dates, units, and scope,” requires the metric definition. Require the geographic basis for each claim. |
| GEO-02 | HIGH | `agents/stock-geopolitics-analyst.md:16` | Linking a regulation to a flow does not establish that it covers the company’s entity, product, or destination. Spec §1 requires the authoritative source for a decision. Require the rule’s covered scope and exceptions; label unresolved applicability as inference or unknown. |
| GEO-03 | MEDIUM | `agents/stock-geopolitics-analyst.md:16,23` | “In force / proposed / rumoured” misses an adopted rule with a future effective date, particularly at a historical `AS_OF`. Spec §1 requires separate publication and event dates. Add effective-date and historical-status checks. |
| GEO-04 | MEDIUM | `agents/stock-geopolitics-analyst.md:15–16,32–33` | The broad exposure and regime lists, followed by a completion condition for every category, invite low-value searches. Spec §§3 and 6 require relevant coverage and materiality. Gate investigation on a sourced exposure and material mechanism. |
| GEO-05 | MEDIUM | `agents/stock-geopolitics-analyst.md:10–12` | `.../agents/...` is not an executable path. The filings reader also runs in parallel under `agents/ORCHESTRATION.md`, so its findings may be absent or stale. Use explicit ROOT-relative paths and treat that output as an optional lead. |
| GEO-06 | MEDIUM | `agents/stock-geopolitics-analyst.md:25` | `SOURCE_LIBRARY.md` marks geopolitical sources untested, while the protocol’s numeric “figure cross-checked” test does not fit legal text. The blanket rule can prevent use of an official rule to establish its own wording. Specify verification of the official host, date, status, and clause; assess company applicability separately. |
| GEO-07 | MEDIUM | `agents/stock-geopolitics-analyst.md:15–16` | Government customers and procurement are requested without an award interpretation rule. Spec §6 distinguishes award ceilings, obligations, outlays, and revenue. Require entity matching and those distinctions; the Sandisk autocomplete miss in the source notes proves only a search miss. |

Revised prompt: [revised/round1/agents/stock-geopolitics-analyst.md](/private/tmp/claude-501/-Users-ali/d4c86359-2e4c-4fbd-8343-299aea24f480/scratchpad/consult2/revised/round1/agents/stock-geopolitics-analyst.md). The original was not changed.

## Acceptance checks

1. With SNDK at `AS_OF` 2026-08-20, use the 10-K filed 2026-08-17 and exclude the 10-Q filed 2026-10-30, as dated in `samples/SNDK_manifest.head.json`.
2. Report the SNDK cache’s two annual reports and six 10-Qs as limited coverage, not evidence that other disclosures never existed.
3. Given only the sample 10-Q header, produce no geographic revenue figure: it contains filing metadata, not a geographic table.
4. Treat the Sandisk `USAspending` autocomplete result of zero as “no matching record in that search,” not “no government business.”

COUNTS: HIGH=2 MEDIUM=5 LOW=0  
CONVERGED: yes

Codex session ID: 01a1bd7f-c845-76e1-a85a-cfe926afaa0d
Resume in Codex: codex resume 01a1bd7f-c845-76e1-a85a-cfe926afaa0d
