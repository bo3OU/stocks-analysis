#!/usr/bin/env python3
"""Local tests for common.Http guards (no internet, no secrets): 429 handling, unsafe redirects, SEC challenge pages,
HTML served as CSV, redaction, cached retrieval time, URL-bound cache. Run: .venv/bin/python -I scripts/test_http_guards.py"""
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Http, Manifest, Redactor, is_public_host  # noqa: E402

HITS: dict[str, int] = {}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        HITS[self.path] = HITS.get(self.path, 0) + 1
        if self.path == "/ratelimited":
            if HITS[self.path] == 1:
                self.send_response(429)
                self.send_header("Retry-After", "1")
                self.end_headers()
                return
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers(); self.wfile.write(b"ok after 429")
        elif self.path == "/redirect-evil":
            self.send_response(302); self.send_header("Location", "https://evil.example.com/steal?auth=SECRET"); self.end_headers()
        elif self.path == "/redirect-http":
            self.send_response(302); self.send_header("Location", "http://www.sec.gov/x"); self.end_headers()
        elif self.path == "/challenge":
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            self.wfile.write(b"<html><title>SEC</title>Request Rate Threshold Exceeded</html>")
        elif self.path == "/htmlcsv":
            self.send_response(200); self.send_header("Content-Type", "text/csv"); self.end_headers(); self.wfile.write(b"<!DOCTYPE html><html>login</html>")
        elif self.path == "/redirect-private":
            self.send_response(302); self.send_header("Location", "https://127.0.0.1/admin"); self.end_headers()
        elif self.path == "/big":
            self.send_response(200); self.send_header("Content-Type", "application/octet-stream"); self.end_headers(); self.wfile.write(b"x" * 5000)
        elif self.path == "/good.csv":
            self.send_response(200); self.send_header("Content-Type", "text/csv"); self.send_header("Content-Disposition", "attachment; filename=x_usd_01-01-2026.csv")
            self.end_headers(); self.wfile.write(b"a,b\n1,2\n")
        else:
            self.send_response(404); self.end_headers()


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if not cond else ""))
    if not cond:
        fails.append(name)


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    man = Manifest("T", Redactor(["SECRETTOKEN"]))
    http = Http(man, "test agent test@example.com", root)

    t0 = time.time()
    r = http.get(f"{base}/ratelimited", host="other", dest=root / "a.txt", kind="t")
    check("429 then retry succeeds", r.ok and (root / "a.txt").read_text() == "ok after 429" and HITS["/ratelimited"] == 2, str(r))
    check("429 honoured Retry-After (waited >= 1s)", time.time() - t0 >= 1.0, f"{time.time() - t0:.2f}s")

    r = http.get(f"{base}/redirect-evil", host="sec", dest=root / "b.txt", kind="t")
    check("redirect to unapproved host is blocked, nothing saved", r.status == "blocked" and not (root / "b.txt").exists(), str(r))
    r = http.get(f"{base}/redirect-http", host="finviz", dest=root / "c.txt", kind="t")
    check("redirect to plain http is blocked", r.status == "blocked", str(r))
    check("unsafe redirect is not retried", HITS["/redirect-evil"] == 1 and HITS["/redirect-http"] == 1, str(HITS))

    r = http.get(f"{base}/challenge", host="sec", dest=root / "d.htm", kind="t")
    check("SEC challenge page with HTTP 200 is rejected", r.status == "blocked" and not (root / "d.htm").exists(), str(r))
    r = http.get(f"{base}/htmlcsv", host="finviz", dest=root / "e.csv", kind="t", expect="csv")
    check("HTML served as CSV is rejected", r.status == "unexpected_content" and not (root / "e.csv").exists(), str(r))

    r = http.get(f"{base}/good.csv", host="finviz", dest=root / "f.csv", kind="t", expect="csv")
    check("good CSV accepted, Content-Disposition kept", r.ok and "usd" in (r.content_disposition or ""), str(r))
    r2 = http.get(f"{base}/good.csv", host="finviz", dest=root / "f.csv", kind="t", expect="csv", max_age_h=6)
    check("second call served from cache", r2.status == "cached", str(r2))

    blob = json.dumps(man.entries)
    man.add(kind="x", url="https://elite.finviz.com/export?t=A&auth=SECRETTOKEN&x=1", note="token SECRETTOKEN here", path="p")
    out = root / "m.json"
    man.save(out)
    txt = out.read_text()
    check("manifest is valid JSON and contains no token", "SECRETTOKEN" not in txt and json.loads(txt)["entries"], txt[:80])
    check("redaction keeps surrounding JSON intact", json.loads(txt)["entries"][-1]["url"].endswith("auth=<redacted>&x=1"), txt[-200:])

    # cached entries keep their original retrieval time when the previous manifest is supplied
    old = {"f.csv": {"url": f"{base}/good.csv", "status": "ok", "retrieved_at": "2020-01-01T00:00:00Z"}}
    http2 = Http(Manifest("T", Redactor([])), "test agent test@example.com", root)
    http2.prev = old
    r3 = http2.get(f"{base}/good.csv", host="finviz", dest=root / "f.csv", kind="t", expect="csv", max_age_h=6)
    check("cached entry keeps previous retrieved_at", http2.manifest.entries[-1].get("retrieved_at") == "2020-01-01T00:00:00Z", str(http2.manifest.entries[-1]))

    # URL-bound cache: same path, different URL must not be reused when bind_url=True
    http2.prev = {"f.csv": {"url": f"{base}/other", "status": "ok"}}
    r4 = http2.get(f"{base}/good.csv", host="finviz", dest=root / "f.csv", kind="t", expect="csv", max_age_h=6, bind_url=True)
    check("bind_url refuses to reuse a file fetched from another URL", r4.status != "cached", str(r4))

check("is_public_host rejects loopback, localhost and private names", not any(is_public_host(h) for h in ("127.0.0.1", "localhost", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "foo.local")))
check("is_public_host accepts a public name", is_public_host("www.sec.gov"))

with tempfile.TemporaryDirectory() as td2:
    root2 = Path(td2)
    http3 = Http(Manifest("T", Redactor([])), "test agent test@example.com", root2)
    r = http3.get(f"{base}/redirect-private", host="public:test", dest=root2 / "p.txt", kind="t")
    check("public fetch: redirect to a private address is blocked", r.status == "blocked" and not (root2 / "p.txt").exists(), str(r))
    r = http3.get(f"{base}/big", host="public:test", dest=root2 / "big.bin", kind="t", max_bytes=1000)
    check("public fetch: oversize response refused, nothing saved", r.status == "unexpected_content" and not (root2 / "big.bin").exists(), str(r))
    check("per-host lock files are sanitized", (root2 / "_cache" / "locks" / "public_test.ts").exists(), str(list((root2 / "_cache").rglob("*"))))

import subprocess
for target, label in (("http://www.sec.gov/x", "plain http"), ("https://127.0.0.1/x", "loopback IP"), ("https://localhost/x", "localhost"), ("https://example.org:8443/x", "custom port"), ("https://user:pw@example.org/x", "credentials")):
    out = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve().parent / "agent_fetch.py"), "public", target, "--ticker", "SNDK", "--agent", "stock-market-analyst", "--out", str(Path(__file__).resolve().parent.parent / "research/SNDK/agents/stock-market-analyst/work/downloads/t.html")], capture_output=True, text=True)
    check(f"agent_fetch public refuses {label}", '"refused"' in out.stdout, out.stdout[:120] + out.stderr[-120:])

print(f"\n{'ALL PASSED' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
