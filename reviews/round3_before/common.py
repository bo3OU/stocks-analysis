"""Shared helpers: env loading, rate limiting, HTTP with bounded retries, redaction, manifest.

Rules baked in (from the tested skills):
- SEC requests always carry the declared SEC_USER_AGENT. Never a browser User-Agent.
- Other hosts get the honest default python-requests User-Agent.
- Sequential requests only, with a minimum interval per host (well under SEC 10 req/s, Finviz 10 req/5 s).
- Bounded retries: 429 honours Retry-After; 5xx and connection errors back off; 403/404 are final (never circumvented).
- The Finviz token is never written to disk (manifest, logs, filenames).
"""
from __future__ import annotations

import datetime as dt
import email.utils
import fcntl
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, quote_plus, urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

# minimum seconds between requests, per host key
INTERVALS = {"sec": 0.25, "finviz": 0.6, "finra": 0.4, "treasury": 0.5, "other": 0.5}


def load_env(path: Path = ENV_PATH) -> dict:
    env: dict = {}
    if not path.is_file():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class Redactor:
    def __init__(self, secrets: list[str]):
        self.secrets = [variant for s in secrets if s for variant in (s, quote(s, safe=""), quote_plus(s))]

    def __call__(self, text: str) -> str:
        for s in self.secrets:
            text = text.replace(s, "<redacted>")
        return re.sub(r"(auth=)[^&#\s]+", r"\1<redacted>", text, flags=re.IGNORECASE)


class Manifest:
    def __init__(self, ticker: str, redact: Redactor):
        self.ticker = ticker
        self.redact = redact
        self.entries: list[dict] = []

    def _clean(self, value):
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {k: self._clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._clean(v) for v in value]
        return value

    def add(self, **kw) -> dict:
        kw["id"] = len(self.entries) + 1
        kw.setdefault("retrieved_at", utcnow_iso())
        kw = self._clean(kw)
        self.entries.append(kw)
        return kw

    def save(self, path: Path, extra: dict | None = None) -> None:
        data = {"ticker": self.ticker, "generated_at": utcnow_iso(), **(extra or {}), "entries": self.entries}
        path.write_text(json.dumps(self._clean(data), indent=1))


class UnsafeRedirect(Exception):
    pass


class RateLimited(Exception):
    pass


@dataclass
class Result:
    ok: bool
    status: str  # ok | cached | empty | blocked | not_found | unexpected_content | error
    code: int | None
    path: Path | None
    size: int = 0
    content_disposition: str | None = None


def retry_after_seconds(value: str | None, default: int = 5, cap: int | None = 120) -> int:
    """Retry-After may be delta-seconds or an HTTP date."""
    if not value:
        return default
    try:
        seconds = max(0, int(float(value)))
        return min(seconds, cap) if cap is not None else seconds
    except (ValueError, OverflowError):
        try:
            when = email.utils.parsedate_to_datetime(value)
            seconds = max(0, int((when - dt.datetime.now(when.tzinfo)).total_seconds()))
            return min(seconds, cap) if cap is not None else seconds
        except (TypeError, ValueError):
            return default


SOURCES = {"sec": "sec-edgar", "finviz": "finviz-elite", "finra": "finra", "treasury": "us-treasury", "other": "other"}


class Http:
    def __init__(self, manifest: Manifest, sec_user_agent: str, out_root: Path, force: bool = False):
        self.manifest = manifest
        self.session = requests.Session()
        self.sec_ua = sec_user_agent
        self.out_root = out_root  # manifest paths are relative to this
        self.force = force  # ignore cached files
        self.prev: dict[str, dict] = {}  # previous manifest entries by path, to carry headers over for cached files
        self._last: dict[str, float] = {}

    def _wait(self, host: str) -> None:
        """Global request gap and any shared Retry-After deadline."""
        gap = INTERVALS.get(host, 0.5)
        lock_dir = self.out_root / "_cache" / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        with open(lock_dir / f"{host}.ts", "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                raw = f.read().strip()
                last = float(raw) if raw else 0.0
                delta = time.time() - last
                if delta < gap:
                    delay = gap - delta
                    if delay > 120:
                        raise RateLimited(f"{host} Retry-After has {delay:.0f}s remaining")
                    time.sleep(delay)
                f.seek(0)
                f.truncate()
                f.write(str(time.time()))
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _defer(self, host: str, seconds: int) -> None:
        """Share a 429 deadline with every process using this research root."""
        lock_dir = self.out_root / "_cache" / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        with open(lock_dir / f"{host}.ts", "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                raw = f.read().strip()
                deadline = max(float(raw) if raw else 0.0, time.time() + seconds)
                f.seek(0)
                f.truncate()
                f.write(str(deadline))
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def get(self, url: str, *, host: str, dest: Path, kind: str, source: str | None = None,
            immutable: bool = False, max_age_h: float | None = None, expect: str | None = None,
            meta: dict | None = None, retries: int = 3, bind_url: bool = False) -> Result:
        """Download url to dest. immutable=True: reuse forever if present (accession documents).
        max_age_h: reuse if younger than this many hours. expect: substring required in Content-Type."""
        meta = meta or {}
        source = source or SOURCES.get(host, host)

        def rel(p: Path) -> str:
            try:
                return str(p.relative_to(self.out_root))
            except ValueError:
                return str(p)

        prior = self.prev.get(rel(dest))
        same_url = (prior is not None and prior.get("url") == self.manifest.redact(url)
                    and prior.get("status") in {"ok", "cached"})
        cache_valid = False
        if dest.is_file() and dest.stat().st_size > 0:
            with dest.open("rb") as cached_file:
                prefix = cached_file.read(4096).lower().lstrip()
            cache_valid = not (host == "sec" and any(x in prefix for x in (
                b"request rate threshold exceeded", b"access denied", b"captcha", b"verify you are human")))
            cache_valid = cache_valid and not (expect == "csv" and prefix.startswith((b"<!doctype html", b"<html")))
        if cache_valid and not self.force and (same_url or not bind_url):
            age_h = (time.time() - dest.stat().st_mtime) / 3600
            if immutable or (max_age_h is not None and age_h <= max_age_h):
                prev_e = self.prev.get(rel(dest)) or {}
                disp = prev_e.get("content_disposition")
                extra = {"content_disposition": disp} if disp else {}
                # a cached file keeps the time it was actually retrieved (not the time it was reused)
                retrieved = prev_e.get("retrieved_at") or dt.datetime.fromtimestamp(
                    dest.stat().st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                self.manifest.add(kind=kind, source=source, url=url, path=rel(dest), status="cached",
                                  bytes=dest.stat().st_size, retrieved_at=retrieved, **extra, **meta)
                return Result(True, "cached", None, dest, dest.stat().st_size, disp)

        headers = {}
        if host == "sec":
            headers["User-Agent"] = self.sec_ua
        status, code, note = "error", None, ""
        for attempt in range(retries):
            try:
                request_url = url
                for _ in range(4):
                    self._wait(host)
                    r = self.session.get(request_url, headers=headers, timeout=90, allow_redirects=False)
                    if r.status_code not in (301, 302, 303, 307, 308):
                        break
                    location = r.headers.get("Location")
                    if not location:
                        break
                    next_url = urljoin(request_url, location)
                    parsed = urlparse(next_url)
                    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment:
                        raise UnsafeRedirect("unsafe redirect")
                    if host == "sec" and parsed.netloc.lower() not in {"www.sec.gov", "data.sec.gov", "efts.sec.gov"}:
                        raise UnsafeRedirect("SEC redirect to unapproved host")
                    if host == "finviz" and parsed.netloc.lower() != "elite.finviz.com":
                        raise UnsafeRedirect("Finviz redirect to unapproved host")
                    request_url = next_url
                else:
                    raise requests.RequestException("too many redirects")
            except RateLimited as e:
                status, note = "blocked", str(e)
                break
            except UnsafeRedirect as e:
                status, note = "blocked", f"redirect refused: {e}"
                break
            except requests.RequestException as e:
                note = type(e).__name__
                time.sleep(2 * (attempt + 1))
                continue
            code = r.status_code
            if code == 200:
                ctype = r.headers.get("Content-Type", "").lower()
                body = r.content
                prefix = body[:4096].lower().lstrip()
                challenge = host == "sec" and any(x in prefix for x in (
                    b"request rate threshold exceeded", b"access denied", b"captcha", b"verify you are human"))
                html_in_csv = expect == "csv" and prefix.startswith((b"<!doctype html", b"<html"))
                if len(body) == 0:
                    status = "empty"
                elif challenge:
                    status, note = "blocked", "SEC challenge page"
                elif (expect and expect not in ctype) or html_in_csv:
                    status, note = "unexpected_content", f"content-type {ctype!r} or HTML body"
                else:
                    status = "ok"
                if status != "ok":
                    self.manifest.add(kind=kind, source=source, url=url, path=None, status=status,
                                      http=code, bytes=len(body), note=note, **meta)
                    return Result(False, status, code, None, len(body))
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".tmp")
                tmp.write_bytes(body)
                os.replace(tmp, dest)
                disp = r.headers.get("Content-Disposition")
                extra = {"content_disposition": disp} if disp else {}
                self.manifest.add(kind=kind, source=source, url=url, path=rel(dest), status=status, http=code,
                                  bytes=len(body), note=note, **extra, **meta)
                return Result(status == "ok", status, code, dest, len(body), disp)
            if code == 429:
                wait = retry_after_seconds(r.headers.get("Retry-After"), cap=None) + 1
                note = f"429 retry-after {wait - 1}s"
                self._defer(host, wait)
                if wait > 120 or attempt == retries - 1:
                    status = "blocked"
                    break
                continue
            if code >= 500:
                note = f"HTTP {code}"
                time.sleep(2 * (attempt + 1))
                continue
            if code == 403:
                status = "blocked"
            elif code == 404:
                status = "not_found"
            else:
                status = "error"
            break
        self.manifest.add(kind=kind, source=source, url=url, path=None, status=status, http=code, note=note, **meta)
        return Result(False, status, code, None)
