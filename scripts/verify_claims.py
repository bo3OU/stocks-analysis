"""Mechanical checks on agents' claims.jsonl, run before the reconciler or the report. It does not judge truth.

Checks per claim: JSON and required fields; label in FACT/CLAIM/CALC/INFERENCE/UNKNOWN; unique IDs with one prefix per agent;
source exists inside the folder or a time-compatible sibling peer cache (or is an http(s) URL); cited line numbers fall inside a cached text file; numbers written in the
statement appear in the cited lines (or file) -> WARN if not; depends_on IDs exist; CALC/INFERENCE carry dependencies; dates well formed.
Writes RESEARCH_DIR/tables/claims_check.csv and prints a summary. Exit code 1 if any ERROR.
Usage: .venv/bin/python -I scripts/verify_claims.py <TICKER or RESEARCH_DIR> [--agent NAME]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE if (HERE / "toolkit.py").is_file() else HERE.parents[2] / "scripts"))
from toolkit import RESEARCH, _numbered_lines, fail, research_dir, write_csv  # noqa: E402

REQUIRED = ["claim_id", "agent", "label", "statement", "source", "location", "published", "origin", "confidence"]
LABELS = {"FACT", "CLAIM", "CALC", "INFERENCE", "UNKNOWN"}
NUM_RE = re.compile(r"(?<![\w.])\$?-?\d[\d,]*(?:\.\d+)?")
LINES_RE = re.compile(r"\blines?\s+(\d+)(?:\s*[-–]\s*(\d+))?", re.I)
L_RE = re.compile(r"\bL(\d+)(?:\s*[-–]\s*L?(\d+))?\b")


def numbers(text: str) -> set[str]:
    out = set()
    for m in NUM_RE.findall(text or ""):
        d = re.sub(r"[^\d.]", "", m).strip(".")
        if len(re.sub(r"\D", "", d)) >= 3:  # ignore tiny numbers (years, counts, ids)
            out.add(d.rstrip("0").rstrip(".") if "." in d else d)
    return out


def cited_ranges(loc: str) -> list[tuple[int, int]]:
    rs = []
    for rx in (LINES_RE, L_RE):
        for m in rx.finditer(loc or ""):
            a = int(m.group(1))
            b = int(m.group(2) or a)
            rs.append((a, b))
    return rs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--agent")
    a = ap.parse_args()
    rd = research_dir(a.folder)
    if (rd / "agents").is_symlink():
        fail("agents directory is a symlink")
    res: list[dict] = []
    claims: list[tuple[str, int, dict]] = []

    def note(agent, cid, check, status, detail):
        res.append({"agent": agent, "claim_id": cid, "check": check, "status": status, "detail": detail})

    all_claims: list[tuple[str, int, dict]] = []
    for cf in sorted((rd / "agents").glob("*/claims.jsonl")):
        agent = cf.parent.name
        if cf.is_symlink() or cf.parent.is_symlink():
            if not a.agent or agent == a.agent:
                note(agent, "", "file", "ERROR", "claims.jsonl is a symlink")
            continue
        for i, line in enumerate(cf.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                if not isinstance(d, dict):
                    raise ValueError("not an object")
            except ValueError as e:
                if not a.agent or agent == a.agent:
                    note(agent, f"line {i}", "json", "ERROR", str(e))
                continue
            all_claims.append((agent, i, d))
    claims = [x for x in all_claims if not a.agent or x[0] == a.agent]
    if not claims:
        note(a.agent or "", "", "file", "ERROR", "no claims found")
    ids = collections.Counter(str(d.get("claim_id", "")) for _, _, d in all_claims)
    all_ids = {k for k in ids if k}
    prefixes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    text_cache: dict[Path, list[str]] = {}
    for agent, i, d in claims:
        cid = str(d.get("claim_id", f"line {i}"))
        missing = [k for k in REQUIRED if k not in d or d[k] is None or d[k] == ""]
        if missing:
            note(agent, cid, "required_fields", "ERROR", "missing " + ", ".join(missing))
        wrong_types = [k for k in REQUIRED if k in d and d[k] is not None and not isinstance(d[k], str)]
        if wrong_types:
            note(agent, cid, "required_fields", "ERROR", "not strings: " + ", ".join(wrong_types))
        if d.get("confidence") not in ("high", "medium", "low"):
            note(agent, cid, "confidence", "WARN", "confidence should be exactly high, medium or low (put nuance in confidence_reason)")
        if d.get("agent") != agent:
            note(agent, cid, "agent_field", "ERROR", f"agent field {d.get('agent')!r} differs from folder {agent}")
        if not isinstance(d.get("label"), str) or d.get("label") not in LABELS:
            note(agent, cid, "label", "ERROR", f"label {d.get('label')!r}")
        if not isinstance(d.get("claim_id"), str) or not d.get("claim_id"):
            note(agent, cid, "claim_id", "ERROR", "claim_id must be a nonempty string")
        if ids[cid] > 1:
            note(agent, cid, "unique_id", "ERROR", f"{ids[cid]} claims share this ID")
        prefixes[agent][re.sub(r"[-_]?\d+$", "", cid)] += 1
        pub = str(d.get("published", ""))
        if pub != "unknown":
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pub):
                    raise ValueError("not YYYY-MM-DD")
                dt.date.fromisoformat(pub)
            except ValueError:
                note(agent, cid, "published", "ERROR", f"published {pub!r} is not an ISO date or 'unknown'")
        av = d.get("available_at")
        if av:
            try:
                if dt.datetime.fromisoformat(str(av).replace("Z", "+00:00")).tzinfo is None:
                    note(agent, cid, "available_at", "WARN", "available_at lacks a timezone")
            except ValueError:
                if str(av) != "unknown":
                    note(agent, cid, "available_at", "WARN", f"available_at {av!r} unparseable")
        deps = d.get("depends_on") or []
        if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
            note(agent, cid, "depends_on", "ERROR", "depends_on must be a list of claim IDs")
            deps = []
        for dep in deps:
            if dep not in all_ids:
                note(agent, cid, "depends_on", "ERROR", f"unknown claim ID {dep}")
        if d.get("label") in ("CALC", "INFERENCE") and not deps:
            note(agent, cid, "depends_on", "WARN" if d.get("label") == "CALC" else "ERROR", f"{d.get('label')} without depends_on")
        src = str(d.get("source", ""))
        if src.lower() == "not obtained" and d.get("label") != "UNKNOWN":
            note(agent, cid, "source_exists", "ERROR", "only UNKNOWN may use 'not obtained'")
        if d.get("label") == "UNKNOWN" and src.lower() == "not obtained":
            continue
        if re.match(r"https?://", src):
            if not d.get("retrieved_at") and not d.get("available_at") and not str(d.get("published", "")).startswith("20"):
                note(agent, cid, "url_dating", "WARN", "URL source without retrieved_at, available_at or a publication date")
            continue
        try:  # Peer citations must name a direct sibling cache on the same time basis.
            raw = Path(src)
            p = (rd / raw).resolve()
            if not p.is_relative_to(rd):
                parts = raw.parts
                if raw.is_absolute() or len(parts) < 3 or parts[0] != ".." or any(part == ".." for part in parts[1:]):
                    raise ValueError("not a direct peer citation")
                peer_root = RESEARCH / parts[1]
                if peer_root.is_symlink() or peer_root.resolve().parent != RESEARCH.resolve() or peer_root.name.startswith("_"):
                    raise ValueError("not a peer research folder")
                if not p.is_relative_to(peer_root.resolve()) or not (peer_root / "identity.json").is_file() or (peer_root / "identity.json").is_symlink():
                    raise ValueError("peer source escapes its folder")
                if (rd / "identity.json").is_symlink():
                    raise ValueError("current cache identity is a symlink")
                current_id = json.loads((rd / "identity.json").read_text(encoding="utf-8"))
                peer_id = json.loads((peer_root / "identity.json").read_text(encoding="utf-8"))
                if not isinstance(current_id, dict) or not isinstance(peer_id, dict):
                    raise ValueError("invalid peer identity")
                basis = lambda d: (d.get("mode"), d.get("as_of_utc") if d.get("mode") == "as_of" else None)
                if basis(current_id) != basis(peer_id) or basis(current_id)[0] not in ("live", "as_of") or (basis(current_id)[0] == "as_of" and not basis(current_id)[1]):
                    raise ValueError("peer cache has a different mode or cutoff")
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            note(agent, cid, "source_exists", "ERROR", f"source outside folder or incompatible peer: {src[:120]} ({exc})")
            continue
        if not p.is_file():
            alt = (rd / "agents" / agent / src).resolve()
            if alt.is_relative_to(rd) and alt.is_file():
                note(agent, cid, "source_relative", "WARN", f"source resolves only relative to the agent folder: {src}")
                continue
            note(agent, cid, "source_exists", "ERROR", f"source not found: {src[:120]}")
            continue
        if p.suffix.lower() not in (".txt", ".csv", ".md", ".json", ".jsonl"):
            continue
        if p not in text_cache:
            text_cache[p] = _numbered_lines(p.read_text(encoding="utf-8", errors="replace"))
        lines = text_cache[p]
        ranges = cited_ranges(str(d.get("location", "")))
        bad = [r for r in ranges if r[0] < 1 or r[1] < r[0] or r[1] > len(lines)]
        if bad:
            note(agent, cid, "location_range", "ERROR", f"cited lines {bad} outside {src} ({len(lines)} lines)")
        nums = numbers(str(d.get("statement", ""))) if d.get("label") in ("FACT", "CLAIM") else set()
        if nums:
            hay = " ".join(" ".join(lines[max(r[0] - 1, 0):r[1]]) for r in ranges if r not in bad) if ranges and not bad else " ".join(lines)
            hay_nums = numbers(hay)
            absent = sorted(n for n in nums if n not in hay_nums)
            where = "cited lines" if ranges and not bad else "whole file (no line range cited)"
            if absent and len(absent) == len(nums):
                note(agent, cid, "numbers_in_source", "WARN", f"none of {sorted(nums)[:6]} found in {where}")
            elif absent:
                note(agent, cid, "numbers_in_source", "WARN", f"not found in {where}: {absent[:6]}")
    for agent, c in prefixes.items():
        if len(c) > 1:
            note(agent, "", "id_prefix", "WARN", f"several ID prefixes: {dict(c)}")
    out = rd / "tables"
    if out.is_symlink() or not out.resolve().is_relative_to(rd):
        fail("tables directory escapes folder")
    write_csv(out / "claims_check.csv", ["agent", "claim_id", "check", "status", "detail"], res)
    by = collections.Counter((r["status"]) for r in res)
    print(f"{len(claims)} claims checked; ERROR {by['ERROR']}, WARN {by['WARN']}; details in tables/claims_check.csv")
    for r in [x for x in res if x["status"] == "ERROR"][:25]:
        print(f"ERROR {r['agent']} {r['claim_id']} {r['check']}: {r['detail']}")
    sys.exit(1 if by["ERROR"] else 0)


if __name__ == "__main__":
    main()
