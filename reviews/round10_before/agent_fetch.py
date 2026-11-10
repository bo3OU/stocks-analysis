#!/usr/bin/env python3
"""Guarded single-URL fetch for agents: SEC documents or Finviz Elite exports that fetch_company.py did not pull.

  agent_fetch.py sec URL --ticker T --agent stock-AGENT --out research/T/agents/stock-AGENT/work/downloads/name [--text]
  agent_fetch.py public https://example.org/page --ticker T --agent stock-AGENT --out research/T/agents/stock-AGENT/work/downloads/name.html
  agent_fetch.py finviz "export/stock?t=SNDK&ty=si" --ticker SNDK --agent stock-AGENT --out research/SNDK/agents/stock-AGENT/work/downloads/name.csv

Guards (so an agent cannot misuse credentials or write into the data it must not edit):
- sec: https only, hosts www.sec.gov / data.sec.gov / efts.sec.gov; sends the declared SEC User-Agent from .env.
- public: https only, no credentials or secret-like query keys, custom port, SEC/Finviz host, localhost or
  private address; redirects re-checked on every hop, 1 s gap per host shared across processes, 50 MB cap.
- finviz: path must start with 'export/' on elite.finviz.com; the token is appended here and never printed or stored;
  caller-supplied credential query keys are rejected. SEC targets use the same query guard.
- output must be inside research/<TICKER>/agents/<agent>/ (never raw/, text/, derived/ of the fetch script).
- one global rate budget shared with every other process (cross-process lock in common.py).
- accepted calls and refusals with a validated agent path are appended to work/fetches.jsonl;
  refused targets are not stored. Invalid output paths are reported only on stdout.
Prints one JSON line: status, http, bytes, path, retrieved_at, final_url, text_path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import datetime as dt
import dataclasses
import csv
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import Http, Manifest, Redactor, ROOT, forbidden_public_name, has_credential_query, load_env, public_url_host, utcnow_iso  # noqa: E402
from asof import SI_LAG_DAYS, truncate_price_csv, truncate_si_csv  # noqa: E402
from html_to_text import convert  # noqa: E402

RESEARCH = ROOT / "research"
SEC_HOSTS = {"www.sec.gov", "data.sec.gov", "efts.sec.gov"}
TICKER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")  # research folder name: TICKER (hyphens for dots) or TICKER_asof_<stamp>
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
        return fail("invalid research folder name or agent (use the folder name printed by fetch_company.py, e.g. BRK-B or SNDK_asof_20261029T2000Z)")
    allowed = RESEARCH / args.ticker / "agents" / args.agent / "work" / "downloads"
    asof_meta = None
    meta_path = RESEARCH / args.ticker / "asof.json"
    if meta_path.is_file() and not meta_path.is_symlink():
        try:
            asof_meta = json.loads(meta_path.read_text())
            asof_utc = dt.datetime.fromisoformat(asof_meta["as_of_utc"].replace("Z", "+00:00"))
        except (ValueError, KeyError, OSError):
            return fail("asof.json in the research folder is unreadable")
    if out == allowed or not out.is_relative_to(allowed):
        return fail("output must be in the declared agent's work/downloads directory")
    log = allowed.parent / "fetches.jsonl"

    def append_record(entry: dict) -> bool:
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "a") as f:
                f.write(json.dumps(entry) + "\n")
            return True
        except OSError:
            return False

    def refuse(msg: str) -> int:
        if not append_record({"ts": utcnow_iso(), "kind": args.kind, "status": "refused", "error": msg}):
            return fail("fetch log unavailable")
        return fail(msg)

    if args.max_age_h is not None and args.max_age_h < 0:
        return refuse("max-age-h must be nonnegative")

    env = load_env()
    redact = Redactor([env.get("FINVIZ_AUTH_TOKEN", "")])
    if any(secret in args.target for secret in redact.secrets):
        return refuse("target contains a configured credential")
    if args.kind == "sec":
        u = urlparse(args.target)
        if u.scheme != "https" or u.netloc.lower() not in SEC_HOSTS or u.fragment or has_credential_query(u.query):
            return refuse(f"sec fetch allows https URLs on {sorted(SEC_HOSTS)} and no credential query keys")
        if asof_meta:
            m = re.fullmatch(r"/Archives/edgar/data/\d+/(\d{18})/.*", u.path)
            if m:
                d = m.group(1)
                accession = f"{d[:10]}-{d[10:12]}-{d[12:]}"
                idx_file = RESEARCH / args.ticker / "filings_index.csv"
                eligible = {r["accessionNumber"] for r in csv.DictReader(idx_file.open())} if idx_file.is_file() else set()
                if accession not in eligible:
                    return refuse(f"AS-OF folder: accession {accession} is not in this folder's filings_index.csv (accepted after the cutoff or outside the index window)")
            elif not (u.netloc.lower() == "www.sec.gov" and u.path == "/files/company_tickers.json"):
                return refuse("AS-OF folder: this SEC source is a live, unfiltered listing; only documents of filings in this folder's filings_index.csv can be fetched")
        url, host = args.target, "sec"
        immutable = "/Archives/edgar/data/" in u.path and not u.path.endswith("index.json")
    elif args.kind == "public":
        public_name = public_url_host(args.target)
        if not public_name:
            return refuse("public fetch needs an https URL without credentials, secret query keys, fragment or custom port")
        if forbidden_public_name(public_name):
            return refuse("public fetch refuses SEC/Finviz, local and non-public IP hosts")
        url, host, immutable = args.target, f"public:{public_name}", False
    else:
        t = args.target.lstrip("/")
        p = urlparse(t)
        if (not (p.path == "export" or p.path.startswith("export/")) or not p.query or p.fragment
                or p.scheme or p.netloc or "\\" in t or has_credential_query(p.query)):
            return refuse("finviz target must be an export path with no credential query keys")
        if not env.get("FINVIZ_AUTH_TOKEN"):
            return refuse("FINVIZ_AUTH_TOKEN not configured")
        finviz_trunc = None
        if asof_meta:
            qs = dict(parse_qsl(p.query, keep_blank_values=True))
            ty = qs.get("ty", "c").lower()
            if p.path == "export/stock" and ty in ("c", "si"):
                finviz_trunc = "si" if ty == "si" else "price"
            else:
                return refuse("AS-OF folder: this Finviz export is a live snapshot and cannot be used at the cutoff; only daily price history (ty omitted or c) and short-interest history (ty=si) are available, cut at the cutoff")
        url, host, immutable = f"https://elite.finviz.com/{t}&auth={env['FINVIZ_AUTH_TOKEN']}", "finviz", False

    if args.kind == "sec" and not env.get("SEC_USER_AGENT"):
        return refuse("SEC_USER_AGENT not configured")

    if args.kind != "finviz":
        finviz_trunc = None
    prior = None
    if log.exists():
        if log.is_symlink() or not log.is_file():
            return fail("fetch log must be a regular file")
        for line in log.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("path") == rel:
                prior = entry
    if out.exists() and (prior is None or prior.get("url") != redact(url)):
        return refuse("output exists without a matching URL record; choose a new filename")

    man = Manifest("agent", redact)
    http = Http(man, env.get("SEC_USER_AGENT", ""), RESEARCH)
    if prior is not None:
        http.prev = {out.relative_to(RESEARCH).as_posix(): prior}
    dest = out.with_name(out.name + ".unfiltered") if finviz_trunc else out
    res = http.get(url, host=host, dest=dest, kind=f"agent_{args.kind}", immutable=immutable,
                   max_age_h=6 if args.max_age_h is None else args.max_age_h,
                   expect="csv" if args.kind == "finviz" else None, bind_url=True,
                   max_bytes=50_000_000 if args.kind == "public" else 200_000_000)
    asof_note = None
    if finviz_trunc and (res.ok or res.status == "cached") and res.path:
        try:
            if finviz_trunc == "price":
                kept, dropped, last = truncate_price_csv(res.path, out, asof_utc)
            else:
                kept, dropped, last = truncate_si_csv(res.path, out, asof_utc, asof_meta.get("short_interest_lag_days", SI_LAG_DAYS))
        finally:
            res.path.unlink(missing_ok=True)  # never leave the unfiltered (future) data in the agent folder
        res = dataclasses.replace(res, path=out, size=out.stat().st_size, status="ok")
        asof_note = {"as_of_utc": asof_meta["as_of_utc"], "rows_kept": kept, "rows_dropped_after_cutoff": dropped, "newest_row": last}
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
            fd, tmp_name = tempfile.mkstemp(prefix=tp.name + ".", suffix=".tmp", dir=tp.parent)
            os.close(fd)
            try:
                ok, note = convert(res.path, Path(tmp_name), f"# SOURCE: {redact(url)}\n# retrieved {retrieved_at}")
                if ok:
                    os.replace(tmp_name, tp)
                    text_path = str(tp.relative_to(ROOT))
                else:
                    text_error = redact(note)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
        else:
            text_error = f"unsupported text conversion: {suffix}"
    result = {"status": res.status, "http": res.code, "bytes": res.size,
              "retrieved_at": retrieved_at, "final_url": redact(res.final_url or "") or None,
              "path": str(res.path.relative_to(ROOT)) if res.path else None, "text_path": text_path,
              "text_error": text_error, "content_type": res.content_type,
              "content_disposition": redact(res.content_disposition or "") or None}
    if asof_note:
        result["as_of"] = asof_note
    if not append_record({"ts": utcnow_iso(), "kind": args.kind, "url": redact(url), **result}):
        return fail("fetch log unavailable")
    print(json.dumps(result))
    return 0 if res.ok or res.status == "cached" else 1


if __name__ == "__main__":
    sys.exit(main())
