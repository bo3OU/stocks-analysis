#!/usr/bin/env python3
"""Guarded single-URL fetch for agents: SEC documents or Finviz Elite exports that fetch_company.py did not pull.

  agent_fetch.py sec URL --ticker T --agent stock-AGENT --out research/T/agents/stock-AGENT/work/downloads/name [--text]
  agent_fetch.py public https://example.org/page --ticker T --agent stock-AGENT --out research/T/agents/stock-AGENT/work/downloads/name.html
  agent_fetch.py finviz "export/stock?t=SNDK&ty=si" --ticker SNDK --agent stock-AGENT --out research/SNDK/agents/stock-AGENT/work/downloads/name.csv

Guards (so an agent cannot misuse credentials or write into the data it must not edit):
- sec: https only, hosts www.sec.gov / data.sec.gov / efts.sec.gov; sends the declared SEC User-Agent from .env.
- public: https only, no credentials or credential query keys, custom port, SEC/Finviz host, localhost or
  private address; redirects re-checked on every hop, 1 s gap per host shared across processes, 50 MB cap.
- finviz: path must start with 'export/' on elite.finviz.com; the token is appended here and never printed or stored;
  a caller-supplied 'auth=' is rejected.
- output must be inside research/<TICKER>/agents/<agent>/ (never raw/, text/, derived/ of the fetch script).
- one global rate budget shared with every other process (cross-process lock in common.py).
- every call is appended (token redacted) to the declared agent's work/fetches.jsonl.
Prints one JSON line: status, http, bytes, path, retrieved_at, final_url, text_path.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import Http, Manifest, Redactor, ROOT, forbidden_public_name, load_env, public_url_host, utcnow_iso  # noqa: E402
from html_to_text import convert  # noqa: E402

RESEARCH = ROOT / "research"
SEC_HOSTS = {"www.sec.gov", "data.sec.gov", "efts.sec.gov"}
TICKER_RE = re.compile(r"[A-Z0-9][A-Z0-9-]{0,14}\Z")  # fetch_company.py normalizes dots to hyphens
AGENT_RE = re.compile(r"stock-[a-z0-9-]+\Z")


def fail(msg: str) -> int:
    print(json.dumps({"status": "refused", "error": msg}))
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["sec", "finviz", "public"])
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
        return fail("invalid canonical cache ticker or agent (use BRK-B, not BRK.B)")
    allowed = RESEARCH / args.ticker / "agents" / args.agent / "work" / "downloads"
    if out == allowed or not out.is_relative_to(allowed):
        return fail("output must be in the declared agent's work/downloads directory")
    if args.max_age_h is not None and args.max_age_h < 0:
        return fail("max-age-h must be nonnegative")

    env = load_env() if args.kind != "public" else {}
    redact = Redactor([env.get("FINVIZ_AUTH_TOKEN", "")])
    if args.kind == "sec":
        u = urlparse(args.target)
        if u.scheme != "https" or u.netloc.lower() not in SEC_HOSTS or u.fragment:
            return fail(f"sec fetch allows https URLs on {sorted(SEC_HOSTS)} only")
        url, host = args.target, "sec"
        immutable = "/Archives/edgar/data/" in u.path and not u.path.endswith("index.json")
    elif args.kind == "public":
        public_name = public_url_host(args.target)
        if not public_name:
            return fail("public fetch needs an https URL without credentials, secret query keys, fragment or custom port")
        if forbidden_public_name(public_name):
            return fail("public fetch refuses SEC/Finviz, local and non-public IP hosts")
        url, host, immutable = args.target, f"public:{public_name}", False
    else:
        t = args.target.lstrip("/")
        p = urlparse(t)
        if (not (p.path == "export" or p.path.startswith("export/")) or not p.query or p.fragment
                or p.scheme or p.netloc or "\\" in t or any(k.lower() == "auth" for k, _ in parse_qsl(p.query, keep_blank_values=True))):
            return fail("finviz target must be an export path with query and no auth parameter")
        if not env.get("FINVIZ_AUTH_TOKEN"):
            return fail("FINVIZ_AUTH_TOKEN not configured")
        url, host, immutable = f"https://elite.finviz.com/{t}&auth={env['FINVIZ_AUTH_TOKEN']}", "finviz", False

    if args.kind == "sec" and not env.get("SEC_USER_AGENT"):
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
    http = Http(man, env.get("SEC_USER_AGENT", ""), RESEARCH)
    if prior is not None:
        http.prev = {out.relative_to(RESEARCH).as_posix(): prior}
    res = http.get(url, host=host, dest=out, kind=f"agent_{args.kind}", immutable=immutable,
                   max_age_h=6 if args.max_age_h is None else args.max_age_h,
                   expect="csv" if args.kind == "finviz" else None, bind_url=True,
                   max_bytes=50_000_000 if args.kind == "public" else 200_000_000)
    retrieved_at = (prior.get("retrieved_at") if prior else None) if res.status == "cached" else None
    if res.status == "cached" and not retrieved_at:
        retrieved_at = "unknown"
    if res.status == "ok":
        retrieved_at = utcnow_iso()
    text_path, text_error = None, None
    if args.text and (res.ok or res.status == "cached") and res.path:
        suffix = res.path.suffix.lower()
        if suffix == ".txt":
            text_path = str(res.path.relative_to(ROOT))
        elif suffix in (".htm", ".html", ".pdf"):
            tp = res.path.with_suffix(res.path.suffix + ".txt")
            ok, note = convert(res.path, tp, f"# SOURCE: {redact(url)}\n# retrieved {retrieved_at}")
            text_path = str(tp.relative_to(ROOT)) if ok else None
            text_error = redact(note) if not ok else None
        else:
            text_error = f"unsupported text conversion: {suffix}"
    result = {"status": res.status, "http": res.code, "bytes": res.size,
              "retrieved_at": retrieved_at, "final_url": redact(res.final_url or "") or None,
              "path": str(res.path.relative_to(ROOT)) if res.path else None, "text_path": text_path,
              "text_error": text_error, "content_type": res.content_type,
              "content_disposition": redact(res.content_disposition or "") or None}
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as f:
        f.write(json.dumps({"ts": utcnow_iso(), "kind": args.kind, "url": redact(url), **result}) + "\n")
    print(json.dumps(result))
    return 0 if res.ok or res.status == "cached" else 1


if __name__ == "__main__":
    sys.exit(main())
