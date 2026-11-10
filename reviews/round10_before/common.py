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
import ipaddress
import json
import os
import re
import socket
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, quote, quote_plus, urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

# minimum seconds between requests, per host key
INTERVALS = {"sec": 0.25, "finviz": 0.6, "finra": 0.4, "treasury": 0.5, "other": 0.5, "public": 1.0}


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
    final_url: str | None = None
    content_type: str | None = None


def public_url_host(url: str) -> str | None:
    """Return the HTTPS host only for a public-fetch URL without credential query keys."""
    try:
        u = urlparse(url)
        if (u.scheme != "https" or not u.hostname or u.username is not None or u.password is not None or u.fragment
                or u.port not in (None, 443) or "\\" in u.netloc):
            return None
        if has_credential_query(u.query):
            return None
        return u.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except (ValueError, UnicodeError):
        return None


def has_credential_query(query: str) -> bool:
    """Refuse secret-like keys, including common separator spellings and nested encodings."""
    # Some servers treat ';' as a parameter separator while parse_qsl does not.
    if ";" in query:
        return True
    for key, _ in parse_qsl(query, keep_blank_values=True):
        if "%" in key:  # another decoding pass could turn it into a secret key
            return True
        name = re.sub(r"[^a-z0-9]", "", key.lower())
        if name in {"auth", "authorization", "key", "sig", "code", "jwt", "sid", "oauth", "verifier"}:
            return True
        if any(part in name for part in ("token", "secret", "password", "passwd", "apikey",
                                         "signature", "session", "credential", "bearer", "privatekey",
                                         "accesskey", "subscriptionkey")):
            return True
    return False


def forbidden_public_name(hostname: str) -> bool:
    if hostname in {"sec.gov", "finviz.com"} or hostname.endswith((".sec.gov", ".finviz.com")):
        return True  # these sources must use their dedicated fetch route and rate budget
    if hostname in {"localhost"} or hostname.endswith((".local", ".internal", ".localhost")):
        return True
    try:
        ip = ipaddress.ip_address(hostname)
        return not ip.is_global or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None
                                    and not ip.ipv4_mapped.is_global)
    except ValueError:
        return False


def public_addresses(hostname: str) -> list[tuple]:
    """Resolve once and reject the entire answer if any address is not globally routable."""
    if not hostname or forbidden_public_name(hostname):
        raise UnsafeRedirect("non-public host")
    try:
        infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except OSError:
        raise UnsafeRedirect("host did not resolve") from None
    if not infos:
        raise UnsafeRedirect("host did not resolve")
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            raise UnsafeRedirect("invalid resolved address") from None
        if not ip.is_global or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped and not ip.ipv4_mapped.is_global):
            raise UnsafeRedirect("non-public resolved address")
    return infos


def is_public_host(hostname: str | None) -> bool:
    try:
        public_addresses(hostname or "")
        return True
    except UnsafeRedirect:
        return False


@contextmanager
def pinned_public_dns(hostname: str):
    """Pin the vetted DNS answer through connect; public agent fetches are single-threaded."""
    infos = public_addresses(hostname)
    original = socket.getaddrinfo

    def pinned(host, port, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else str(host)
        if name.lower().rstrip(".") != hostname or str(port) != "443":
            raise socket.gaierror("public fetch refused a different DNS target")
        return infos

    socket.getaddrinfo = pinned
    try:
        yield
    finally:
        socket.getaddrinfo = original


def lock_name(host: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", host)


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
        gap = INTERVALS.get(host.split(":")[0], 0.5)
        lock_dir = self.out_root / "_cache" / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        with open(lock_dir / f"{lock_name(host)}.ts", "a+") as f:
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
        with open(lock_dir / f"{lock_name(host)}.ts", "a+") as f:
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
            meta: dict | None = None, retries: int = 3, bind_url: bool = False, max_bytes: int = 200_000_000) -> Result:
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
                ctype = prev_e.get("content_type")
                extra = {"content_disposition": disp, "content_type": ctype}
                # File modification time is not evidence of first retrieval.
                retrieved = prev_e.get("retrieved_at") or "unknown"
                final_url = prev_e.get("final_url") or (url if same_url else None)
                self.manifest.add(kind=kind, source=source, url=url, path=rel(dest), status="cached",
                                  bytes=dest.stat().st_size, retrieved_at=retrieved, final_url=final_url, **extra, **meta)
                return Result(True, "cached", None, dest, dest.stat().st_size, disp, final_url, ctype)

        headers = {}
        if host == "sec":
            headers["User-Agent"] = self.sec_ua
        status, code, note, final_url = "error", None, "", None
        for attempt in range(retries):
            try:
                request_url = url
                for _ in range(4):
                    public_name = public_url_host(request_url) if host.startswith("public:") else None
                    if host.startswith("public:") and not public_name:
                        raise UnsafeRedirect("invalid public URL")
                    request_host = f"public:{public_name}" if public_name else host
                    self._wait(request_host)
                    if public_name:
                        self.session.trust_env = False  # no proxy can bypass the vetted DNS address
                        with pinned_public_dns(public_name):
                            r = self.session.get(request_url, headers=headers, timeout=90, allow_redirects=False, stream=True)
                    else:
                        r = self.session.get(request_url, headers=headers, timeout=90, allow_redirects=False, stream=True)
                    final_url = request_url
                    if r.status_code not in (301, 302, 303, 307, 308):
                        break
                    location = r.headers.get("Location")
                    r.close()
                    if not location:
                        break
                    try:
                        next_url = urljoin(request_url, location)
                        parsed = urlparse(next_url)
                    except ValueError:
                        raise UnsafeRedirect("malformed redirect URL") from None
                    if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or parsed.fragment:
                        raise UnsafeRedirect("unsafe redirect")
                    if host == "sec" and parsed.netloc.lower() not in {"www.sec.gov", "data.sec.gov", "efts.sec.gov"}:
                        raise UnsafeRedirect("SEC redirect to unapproved host")
                    if host == "finviz" and parsed.netloc.lower() != "elite.finviz.com":
                        raise UnsafeRedirect("Finviz redirect to unapproved host")
                    if host.startswith("public:") and not public_url_host(next_url):
                        raise UnsafeRedirect("redirect to an invalid public URL")
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
                chunks, total = [], 0
                try:
                    for chunk in r.iter_content(65536):
                        total += len(chunk)
                        if total > max_bytes:
                            r.close()
                            self.manifest.add(kind=kind, source=source, url=url, final_url=request_url, path=None,
                                              status="unexpected_content", http=code, bytes=total,
                                              content_type=ctype, note=f"response larger than {max_bytes} bytes", **meta)
                            return Result(False, "unexpected_content", code, None, total, final_url=request_url, content_type=ctype)
                        chunks.append(chunk)
                except requests.RequestException as e:
                    r.close()
                    status, note = "error", type(e).__name__
                    break
                r.close()
                body = b"".join(chunks)
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
                    self.manifest.add(kind=kind, source=source, url=url, final_url=request_url, path=None,
                                      status=status, http=code, bytes=len(body), content_type=ctype, note=note, **meta)
                    return Result(False, status, code, None, len(body), final_url=request_url, content_type=ctype)
                dest.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=dest.parent)
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(body)
                    os.replace(tmp, dest)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                disp = r.headers.get("Content-Disposition")
                extra = {"content_disposition": disp, "content_type": ctype}
                self.manifest.add(kind=kind, source=source, url=url, final_url=request_url,
                                  path=rel(dest), status=status, http=code,
                                  bytes=len(body), note=note, **extra, **meta)
                return Result(status == "ok", status, code, dest, len(body), disp, request_url, ctype)
            if code == 429:
                wait = retry_after_seconds(r.headers.get("Retry-After"), cap=None) + 1
                note = f"429 retry-after {wait - 1}s"
                self._defer(request_host, wait)
                r.close()
                if wait > 120 or attempt == retries - 1:
                    status = "blocked"
                    break
                continue
            if code >= 500:
                note = f"HTTP {code}"
                r.close()
                time.sleep(2 * (attempt + 1))
                continue
            if code == 403:
                status = "blocked"
            elif code == 404:
                status = "not_found"
            else:
                status = "error"
            r.close()
            break
        self.manifest.add(kind=kind, source=source, url=url, final_url=final_url, path=None,
                          status=status, http=code, note=note, **meta)
        return Result(False, status, code, None, final_url=final_url)
