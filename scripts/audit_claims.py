"""Claim-graph audit and recompute for the reconciler and the challenger. Mechanical, not a judgment of truth.

Outputs (RESEARCH_DIR/tables/): claim_priority.csv (claims ranked by how much rests on them), claim_audit.md (origin concentration,
inferences resting on a single origin, dependency cycles, orphan dependencies, recompute results).
Recompute: a claim whose source is a JSON file written by scripts/valuation_calc.py (it echoes inputs) is recomputed with the same
formulas and compared with the stored enterprise value; other CALC claims are listed as not recomputable here.
Usage: .venv/bin/python -I scripts/audit_claims.py <TICKER or RESEARCH_DIR>
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_HERE = HERE if (HERE / "toolkit.py").is_file() else HERE.parents[2] / "scripts"
sys.path.insert(0, str(SOURCE_HERE))
if HERE != SOURCE_HERE:
    sys.path.insert(0, str(HERE))
from toolkit import clean_cell, fail, research_dir, safe_child, write_atomic, write_csv  # noqa: E402
import valuation_calc as vc  # noqa: E402


def load_claims(rd: Path):
    claims, bad = {}, []
    agents = rd / "agents"
    if agents.is_symlink() or safe_child(rd, "agents") is None:
        fail("agents directory escapes research folder")
    for cf in sorted(agents.glob("*/claims.jsonl")):
        if cf.is_symlink() or cf.parent.is_symlink() or safe_child(rd, str(cf.relative_to(rd))) is None:
            bad.append(f"unsafe path: {cf.parent.name}/claims.jsonl")
            continue
        for i, line in enumerate(cf.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                cid = d["claim_id"]
                if not isinstance(cid, str) or not cid.strip():
                    raise ValueError("invalid claim_id")
            except (ValueError, KeyError, TypeError):
                bad.append(f"{cf.parent.name}:{i}")
                continue
            claims.setdefault(cid, []).append({**d, "_agent_dir": cf.parent.name})
    return claims, bad


def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    cycles, state = [], {}
    for root in graph:
        if root in state:
            continue
        state[root] = 1
        path, positions = [root], {root: 0}
        stack = [(root, iter(graph[root]))]
        while stack:
            node, edges = stack[-1]
            nxt = next(edges, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                positions.pop(node)
                path.pop()
            elif nxt in graph and state.get(nxt) == 1:
                cycles.append(path[positions[nxt]:] + [nxt])
            elif nxt in graph and nxt not in state:
                state[nxt] = 1
                positions[nxt] = len(path)
                path.append(nxt)
                stack.append((nxt, iter(graph[nxt])))
    return cycles


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_claims.py <TICKER or RESEARCH_DIR>")
    rd = research_dir(sys.argv[1])
    table_dir = rd / "tables"
    if table_dir.is_symlink() or safe_child(rd, "tables") is None:
        fail("tables directory escapes research folder")
    claims, bad = load_claims(rd)
    flat = [c for cs in claims.values() for c in cs]
    graph = {}
    for cid, cs in claims.items():
        deps = cs[0].get("depends_on") or []
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps):
            bad.append(f"invalid depends_on: {cid}")
            deps = []
        graph[cid] = list(dict.fromkeys(deps))
    dependents = collections.Counter(d for deps in graph.values() for d in deps)
    draft = ""
    for name in ("report_draft.md", "report.md"):
        f = rd / name
        if f.is_file() and not f.is_symlink():
            draft += f.read_text(encoding="utf-8", errors="replace")
    rows = []
    for cid, cs in claims.items():
        c = cs[0]
        in_draft = len(re.findall(r"(?<![\w-])" + re.escape(cid) + r"(?![\w-])", draft))
        rows.append({"claim_id": cid, "agent": c.get("agent", c["_agent_dir"]), "label": c.get("label", ""), "dependents": dependents[cid], "in_report": in_draft,
                     "priority": dependents[cid] * 2 + min(in_draft, 5) * 3 + (2 if c.get("label") == "CALC" else 0) + (1 if c.get("confidence") == "low" else 0),
                     "origin": clean_cell(str(c.get("origin", "")), 80), "statement": clean_cell(str(c.get("statement", "")), 140)})
    rows.sort(key=lambda r: (-r["priority"], r["claim_id"]))
    write_csv(rd / "tables" / "claim_priority.csv", ["claim_id", "agent", "label", "dependents", "in_report", "priority", "origin", "statement"], rows)
    dup = [cid for cid, cs in claims.items() if len(cs) > 1]
    orphans = sorted({(cid, d) for cid, deps in graph.items() for d in deps if d not in claims})
    origin_use = collections.Counter(str(cs[0].get("origin", "")).strip().lower() for cs in claims.values())
    single = []
    for cid, cs in claims.items():
        c = cs[0]
        if c.get("label") == "INFERENCE":
            og = {str(claims[d][0].get("origin", "")).strip().lower() for d in graph[cid] if d in claims}
            if len(og) == 1 and all(d in claims for d in graph[cid]):
                single.append((cid, next(iter(og), "")))
    recompute = []
    for cid, cs in claims.items():
        c = cs[0]
        if c.get("label") != "CALC":
            continue
        src = str(c.get("source", ""))
        p = safe_child(rd, src) if src and not re.match(r"https?://", src) else None
        if p and p.is_file() and p.suffix == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict) and "enterprise_value" in data and "rnpv_inputs" in data:
                    result = vc.rnpv(data["rnpv_inputs"])
                    ev = result["enterprise_value"]
                    stored = vc.finite(data["enterprise_value"], "stored enterprise_value")
                    inputs_match = data.get("inputs") == result["inputs"]
                    ok = inputs_match and abs(ev - stored) <= 1e-6 * max(1.0, abs(ev))
                    recompute.append((cid, src, "file EV matches recomputation; claim value unverified" if ok else
                                      f"MISMATCH stored {data['enterprise_value']} vs recomputed {ev}" +
                                      (" (derived inputs differ from original rNPV inputs)" if not inputs_match else "")))
                    continue
                if isinstance(data, dict) and isinstance(data.get("inputs"), dict) and "enterprise_value" in data and "cash_flows" in data["inputs"]:
                    ev = vc.dcf(data["inputs"])["enterprise_value"]
                    stored = vc.finite(data["enterprise_value"], "stored enterprise_value")
                    ok = abs(ev - stored) <= 1e-6 * max(1.0, abs(ev))
                    recompute.append((cid, src, "file EV matches recomputation; claim value unverified" if ok else
                                      f"MISMATCH stored {data['enterprise_value']} vs recomputed {ev}"))
                    continue
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError, SystemExit):
                recompute.append((cid, src, "could not recompute (invalid inputs)"))
                continue
        recompute.append((cid, src[:70], "not recomputable by this script (agent calculation: reopen its saved script and inputs)"))
    md = [f"# Claim audit: {rd.name}", f"{len(claims)} claims ({len(flat)} rows) from {len(list((rd / 'agents').glob('*/claims.jsonl')))} files. Mechanical checks only.", ""]
    md += [f"## Priority (top 25 of {len(rows)}; see claim_priority.csv)", "Priority = 2 x dependents + 3 x mentions in the report draft (max 5) + 2 if CALC + 1 if low confidence. Verify these first.", ""]
    md += [f"- {r['claim_id']} [{r['label']}] dependents {r['dependents']}, in report {r['in_report']}: {r['statement']}" for r in rows[:25]]
    md += ["", f"## Problems", f"- unparseable claim lines: {', '.join(bad[:10]) or 'none'}", f"- duplicate claim IDs: {', '.join(dup[:10]) or 'none'}",
           f"- dependencies on unknown IDs: {', '.join(f'{a}->{b}' for a, b in orphans[:15]) or 'none'}", f"- dependency cycles: {find_cycles(graph)[:5] or 'none'}"]
    md += ["", "## Origins used by many claims (repeated use of one origin is ONE origin)"]
    md += [f"- {o or '(blank)'}: {n} claims" for o, n in origin_use.most_common(8) if n >= 3]
    md += ["", "## INFERENCE claims whose supporting claims share a single origin"]
    md += [f"- {cid}: only {o or '(blank)'}" for cid, o in single[:20]] or ["- none"]
    md += ["", f"## CALC recompute ({sum(1 for r in recompute if r[2].startswith('file EV matches'))} files matched, {sum(1 for r in recompute if r[2].startswith('MISMATCH'))} mismatched, {sum(1 for r in recompute if 'not recomputable' in r[2])} not recomputable here; claim statements and values are not verified)"]
    md += [f"- {cid} {src}: {res}" for cid, src, res in recompute if not res.startswith("file EV matches")][:30]
    write_atomic(rd / "tables" / "claim_audit.md", "\n".join(md) + "\n")
    print({"claims": len(claims), "cycles": len(find_cycles(graph)), "orphans": len(orphans), "single_origin_inferences": len(single)})


if __name__ == "__main__":
    main()
