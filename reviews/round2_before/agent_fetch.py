#!/usr/bin/env python3
"""Guarded single-URL fetch for agents: SEC documents or Finviz Elite exports that fetch_company.py did not pull.

  agent_fetch.py sec URL --ticker T --agent stock-AGENT --out research/T/agents/stock-AGENT/work/downloads/name [--text]
  agent_fetch.py finviz "export/stock?t=SNDK&ty=si" --ticker SNDK --agent stock-AGENT --out research/SNDK/agents/stock-AGENT/work/downloads/name.csv

Guards (so an agent cannot misuse credentials or write into the data it must not edit):
- sec: https only, hosts www.sec.gov / data.sec.gov / efts.sec.gov; sends the declared SEC User-Agent from .env.
- finviz: path must start with 'export/' on elite.finviz.com; the token is appended here and never printed or stored;
  a caller-supplied 'auth=' is rejected.
- output must be inside research/<TICKER>/agents/<agent>/ (never raw/, text/, derived/ of the fetch script).
- one global rate budget shared with every other process (cross-process lock in common.py).
- every call is appended (token redacted) to the declared agent's work/fetches.jsonl.
Prints one JSON line: status, http, bytes, path, text_path.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import Http, Manifest, Redactor, ROOT, load_env, utcnow_iso  # noqa: E402
from html_to_text import convert  # noqa: E402

RESEARCH = ROOT / "research"
SEC_HOSTS = {"www.sec.gov", "data.sec.gov", "efts.sec.gov"}
TICKER_RE = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,14}\Z")
AGENT_RE = re.compile(r"stock-[a-z0-9-]+\Z")


def fail(msg: str) -> int:
    print(json.dumps({"status": "refused", "error": msg}))
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["sec", "finviz"])
    ap.add_argument("target")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--text", action="store_true", help="also write a plain-text version (.txt) of html/pdf")
    ap.add_argument("--max-age-h", type=float, default=None, help="reuse an existing file younger than this (hours)")
    args = ap.parse_args()

    out = Path(args.out)
    out = out if out.is_absolute() else Path.cwd() / out
    out = out.resolve()
    try:
        rel = out.relative_to(ROOT).as_posix()
    except ValueError:
        return fail(f"output must be inside {ROOT}")
    if not TICKER_RE.fullmatch(args.ticker) or not AGENT_RE.fullmatch(args.agent):
        return fail("invalid ticker or agent")
    allowed = RESEARCH / args.ticker / "agents" / args.agent / "work" / "downloads"
    if out == allowed or not out.is_relative_to(allowed):
        return fail("output must be in the declared agent's work/downloads directory")
    if args.max_age_h is not None and args.max_age_h < 0:
        return fail("max-age-h must be nonnegative")

    env = load_env()
    redact = Redactor([env.get("FINVIZ_AUTH_TOKEN", "")])
    if args.kind == "sec":
        u = urlparse(args.target)
        if u.scheme != "https" or u.hostname not in SEC_HOSTS or u.username or u.password or u.port or u.fragment:
            return fail(f"sec fetch allows https URLs on {sorted(SEC_HOSTS)} only")
        url, host = args.target, "sec"
        immutable = "/Archives/edgar/data/" in u.path and not u.path.endswith("index.json")
    else:
        t = args.target.lstrip("/")
        p = urlparse(t)
        if (not (p.path == "export" or p.path.startswith("export/")) or not p.query or p.fragment
                or p.scheme or p.netloc or "\\" in t or any(k.lower() == "auth" for k, _ in parse_qsl(p.query, keep_blank_values=True))):
            return fail("finviz target must be an export path with query and no auth parameter")
        if not env.get("FINVIZ_AUTH_TOKEN"):
            return fail("FINVIZ_AUTH_TOKEN not configured")
        url, host, immutable = f"https://elite.finviz.com/{t}&auth={env['FINVIZ_AUTH_TOKEN']}", "finviz", False

    if not env.get("SEC_USER_AGENT"):
        return fail("SEC_USER_AGENT not configured")

    log = allowed.parent / "fetches.jsonl"
    prior = None
    if log.exists():
        for line in log.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("path") == rel:
                prior = entry
    if out.exists() and (prior is None or prior.get("url") != redact(url)):
        return fail("output exists without a matching URL record; choose a new filename")

    man = Manifest("agent", redact)
    http = Http(man, env["SEC_USER_AGENT"], RESEARCH)
    if prior is not None:
        http.prev = {out.relative_to(RESEARCH).as_posix(): prior}
    res = http.get(url, host=host, dest=out, kind=f"agent_{args.kind}", immutable=immutable,
                   max_age_h=6 if args.max_age_h is None else args.max_age_h,
                   expect="csv" if args.kind == "finviz" else None, bind_url=True)
    text_path = None
    if args.text and (res.ok or res.status == "cached") and res.path and res.path.suffix.lower() in (".htm", ".html", ".pdf", ".txt"):
        tp = res.path.with_suffix(res.path.suffix + ".txt") if res.path.suffix.lower() != ".txt" else None
        if tp:
            ok, note = convert(res.path, tp, f"# SOURCE: {redact(url)}\n# retrieved {utcnow_iso()}")
            text_path = str(tp.relative_to(ROOT)) if ok else None
    result = {"status": res.status, "http": res.code, "bytes": res.size,
              "path": str(res.path.relative_to(ROOT)) if res.path else None, "text_path": text_path,
              "content_disposition": redact(res.content_disposition or "") or None}
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as f:
        f.write(json.dumps({"ts": utcnow_iso(), "kind": args.kind, "url": redact(url), **result}) + "\n")
    print(json.dumps(result))
    return 0 if res.ok or res.status == "cached" else 1


if __name__ == "__main__":
    sys.exit(main())
