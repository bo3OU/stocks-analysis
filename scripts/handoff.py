"""Orchestrator bookkeeping for agent handoffs.

  handoff.py check    <folder> --agent NAME [--as-of TEXT]   verify findings.md (header, as-of), claims.jsonl and search_log.md exist and parse
  handoff.py save     <folder> --agent NAME [--from FILE|-]  save the findings text an agent returned (subagents cannot write findings.md);
                                                            an existing findings.md is archived into agents/NAME/history/ first
  handoff.py appendix <folder>                               write report_appendix.md: source register, claim ledger, gaps, search-log counts
Usage: .venv/bin/python -I scripts/handoff.py <subcommand> ...
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE if (HERE / "toolkit.py").is_file() else HERE.parents[2] / "scripts"))
from toolkit import clean_cell, fail, research_dir, safe_child, write_atomic  # noqa: E402

AGENT_RE = re.compile(r"^stock-[a-z-]+$")


def agent_dir(rd: Path, agent: str) -> Path:
    if not AGENT_RE.match(agent):
        fail(f"bad agent name: {agent}")
    d = safe_child(rd / "agents", agent)
    if d is None or not d.is_relative_to(rd) or (rd / "agents").is_symlink() or (rd / "agents" / agent).is_symlink():
        fail("agent path escapes the folder")
    return d


def read_claims(p: Path):
    out, bad = [], []
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
        if line.strip():
            try:
                d = json.loads(line)
                out.append(d) if isinstance(d, dict) else bad.append(i)
            except ValueError:
                bad.append(i)
    return out, bad


def header_ok(text: str, agent: str, ticker: str, as_of: str | None = None) -> bool:
    first = text.splitlines()[0] if text.splitlines() else ""
    prefix = f"# {agent} findings: {ticker} as of "
    return first.startswith(prefix) and bool(first[len(prefix):].strip()) and (as_of is None or first[len(prefix):] == as_of.strip())


def cache_ticker(rd: Path) -> str:
    if (rd / "identity.json").is_symlink():
        fail("identity.json is a symlink")
    try:
        identity = json.loads((rd / "identity.json").read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        fail(f"cannot read identity.json: {exc}")
    if not isinstance(identity, dict):
        fail("identity.json must be an object")
    return str(identity.get("ticker") or rd.name.split("_asof_", 1)[0]).replace(".", "-")


def cmd_check(a):
    rd = research_dir(a.folder)
    d = agent_dir(rd, a.agent)
    problems = []
    f = d / "findings.md"
    if f.is_symlink():
        problems.append("findings.md is a symlink")
    elif not f.is_file():
        problems.append("findings.md missing")
    else:
        head = f.read_text(encoding="utf-8", errors="replace").split("\n", 3)
        ticker = cache_ticker(rd)
        if not header_ok(head[0], a.agent, ticker, a.as_of):
            problems.append(f"findings.md header must be '# {a.agent} findings: {ticker} as of <AS_OF>'" + (f" with AS_OF {a.as_of!r}" if a.as_of else ""))
    c = d / "claims.jsonl"
    if c.is_symlink():
        problems.append("claims.jsonl is a symlink")
    elif not c.is_file():
        problems.append("claims.jsonl missing")
    else:
        claims, bad = read_claims(c)
        if not claims:
            problems.append("claims.jsonl has no claims")
        if bad:
            problems.append(f"claims.jsonl has unparseable lines {bad[:5]}")
        required = {"claim_id", "agent", "label", "statement", "source", "location", "published", "origin", "confidence"}
        ids = set()
        for claim in claims:
            invalid = (any(not isinstance(claim.get(k), str) or not claim[k] for k in required)
                       or claim.get("agent") != a.agent
                       or claim.get("label") not in {"FACT", "CLAIM", "CALC", "INFERENCE", "UNKNOWN"})
            if invalid:
                problems.append("claims.jsonl has incomplete or misattributed claims")
                break
            cid = claim["claim_id"]
            if cid in ids:
                problems.append(f"claims.jsonl repeats claim ID {cid}")
                break
            ids.add(cid)
            published = claim["published"]
            if published != "unknown":
                try:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
                        raise ValueError("not YYYY-MM-DD")
                    dt.date.fromisoformat(published)
                except ValueError:
                    problems.append(f"claims.jsonl has invalid published date for {cid}")
                    break
    if (d / "search_log.md").is_symlink():
        problems.append("search_log.md is a symlink")
    elif not (d / "search_log.md").is_file():
        problems.append("search_log.md missing")
    if problems:
        print("BLOCKED: " + "; ".join(problems))
        sys.exit(1)
    print(f"OK {a.agent}: findings.md, claims.jsonl ({len(claims)} claims), search_log.md")


def cmd_save(a):
    rd = research_dir(a.folder)
    d = agent_dir(rd, a.agent)
    text = sys.stdin.read() if a.src in (None, "-") else Path(a.src).read_text(encoding="utf-8")
    ticker = cache_ticker(rd)
    if not header_ok(text.lstrip(), a.agent, ticker):
        fail(f"text does not begin with '# {a.agent} findings: {ticker} as of <AS_OF>'; not saved")
    f = d / "findings.md"
    d.mkdir(parents=True, exist_ok=True)
    if f.is_symlink():
        fail("refusing symlink findings.md")
    fd, tmpname = tempfile.mkstemp(dir=d, prefix=".findings_")
    archived = None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text.lstrip().rstrip("\n") + "\n")
        if f.exists():
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            h = d / "history"
            if h.is_symlink():
                fail("refusing symlink history directory")
            h.mkdir(parents=True, exist_ok=True)
            archived = h / f"findings_{stamp}.md"
            f.replace(archived)
        try:
            os.replace(tmpname, f)
        except OSError:
            if archived is not None:
                archived.replace(f)
            raise
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)
    print(f"saved {f.relative_to(rd)} ({len(text)} chars)")


def cmd_appendix(a):
    rd = research_dir(a.folder)
    if (rd / "agents").is_symlink():
        fail("agents directory is a symlink")
    claims = []
    for cf in sorted((rd / "agents").glob("*/claims.jsonl")):
        if cf.is_symlink() or cf.parent.is_symlink():
            fail(f"refusing symlink claims in {cf.relative_to(rd)}")
        parsed, bad = read_claims(cf)
        if bad:
            fail(f"invalid claims in {cf.relative_to(rd)} at lines {bad[:5]}")
        claims += parsed
    src = collections.defaultdict(lambda: {"n": 0, "agents": set(), "pub": set(), "origin": set()})
    for c in claims:
        s = src[str(c.get("source", ""))]
        s["n"] += 1
        s["agents"].add(str(c.get("agent", "")).replace("stock-", ""))
        s["pub"].add(str(c.get("published", "")))
        s["origin"].add(clean_cell(str(c.get("origin", "")), 70))
    o = [f"# Report appendix: {rd.name}", f"Built by scripts/handoff.py appendix from {len(claims)} claims in agents/*/claims.jsonl. Not a judgment of accuracy; run verify_claims.py too.", "",
         f"## Source register ({len(src)} sources)", "| source | claims | agents | published | origin |", "|---|---|---|---|---|"]
    cell = lambda x, n=160: clean_cell(str(x), n).replace("|", "\\|")  # noqa: E731
    for s, v in sorted(src.items(), key=lambda kv: (-kv[1]["n"], kv[0])):
        o.append(f"| {cell(s, 110)} | {v['n']} | {cell(', '.join(sorted(v['agents'])))} | {cell(', '.join(sorted(v['pub'])), 40)} | {cell('; '.join(sorted(v['origin'])), 120)} |")
    labels = collections.Counter(str(c.get("label")) for c in claims)
    o += ["", "## Claim ledger", "Labels: " + ", ".join(f"{k} {v}" for k, v in sorted(labels.items(), key=lambda kv: str(kv[0]))), "", "| id | label | confidence | statement | source |", "|---|---|---|---|---|"]
    for c in claims:
        o.append("| " + " | ".join(cell(c.get(k, ""), n) for k, n in (("claim_id", 60), ("label", 20), ("confidence", 20), ("statement", 160), ("source", 70))) + " |")
    o += ["", "## Gaps (UNKNOWN claims)"]
    for c in claims:
        if c.get("label") == "UNKNOWN":
            o.append(f"- {c.get('claim_id')}: {clean_cell(str(c.get('statement', '')), 220)}")
    o += ["", "## Search logs (lines per agent)"]
    for sl in sorted((rd / "agents").glob("*/search_log.md")):
        if sl.is_symlink() or sl.parent.is_symlink():
            fail(f"refusing symlink search log in {sl.relative_to(rd)}")
        o.append(f"- {sl.parent.name}: {len(sl.read_text(encoding='utf-8', errors='replace').splitlines())} lines")
    write_atomic(rd / "report_appendix.md", "\n".join(o) + "\n")
    print(f"wrote report_appendix.md ({len(claims)} claims, {len(src)} sources)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "save", "appendix"):
        s = sub.add_parser(name)
        s.add_argument("folder")
        if name != "appendix":
            s.add_argument("--agent", required=True)
        if name == "check":
            s.add_argument("--as-of")
        if name == "save":
            s.add_argument("--from", dest="src")
    a = ap.parse_args()
    {"check": cmd_check, "save": cmd_save, "appendix": cmd_appendix}[a.cmd](a)


if __name__ == "__main__":
    main()
