"""Shared helpers for the offline analysis scripts (digest, ledger, tables, verifiers).

These scripts read only files inside one research folder (research/<TICKER>[_asof_...]). They never fetch, so an
as-of folder stays as-of: whatever fetch_company.py cut at the cutoff is all they can see.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "research"


def fail(msg: str, code: int = 2):
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def research_dir(arg: str) -> Path:
    """Resolve a research folder: a direct child of ROOT/research (not _cache/_logs), holding identity.json."""
    p = Path(arg)
    cands = [p] if p.is_absolute() else [Path.cwd() / p, RESEARCH / p]
    for c in cands:
        try:
            r = c.resolve()
        except OSError:
            continue
        if r.is_dir() and r.parent == RESEARCH.resolve() and not r.name.startswith("_") and (r / "identity.json").is_file():
            return r
    fail(f"not a research folder under {RESEARCH}: {arg} (needs identity.json; run fetch_company.py first)")


def safe_child(base: Path, rel: str) -> Path | None:
    """base/rel resolved, only if it stays inside base (no symlink or .. escape)."""
    try:
        r = (base / rel).resolve()
        r.relative_to(base.resolve())
    except (ValueError, OSError):
        return None
    return r


def write_atomic(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        fail(f"refusing to write through a symlink: {path}")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_csv(path: Path, fields: list[str], rows: list[dict]):
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    write_atomic(path, buf.getvalue())


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def parse_date(s: str | None) -> dt.date | None:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except ValueError:
            continue
    return None


def num(s) -> float | None:
    if s is None:
        return None
    t = str(s).strip().replace(",", "").replace("$", "")
    if t in ("", "-", "--", "N/A", "n/a", "nan"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    d = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def federal_holidays(year: int) -> set[dt.date]:
    """US federal holidays as observed (Saturday -> Friday, Sunday -> Monday), for SEC business-day counts."""
    fixed = [dt.date(year, 1, 1), dt.date(year, 6, 19), dt.date(year, 7, 4), dt.date(year, 11, 11), dt.date(year, 12, 25)]
    out = set()
    for d in fixed + [dt.date(year + 1, 1, 1)]:
        if d.weekday() == 5:
            d -= dt.timedelta(days=1)
        elif d.weekday() == 6:
            d += dt.timedelta(days=1)
        if d.year == year:
            out.add(d)
    out |= {_nth_weekday(year, 1, 0, 3), _nth_weekday(year, 2, 0, 3), _last_weekday(year, 5, 0),
            _nth_weekday(year, 9, 0, 1), _nth_weekday(year, 10, 0, 2), _nth_weekday(year, 11, 3, 4)}
    return out


def is_business_day(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in federal_holidays(d.year)


def add_business_days(d: dt.date, n: int) -> dt.date:
    while n > 0:
        d += dt.timedelta(days=1)
        if is_business_day(d):
            n -= 1
    return d


def fmt(v, nd: int = 2) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def clean_cell(s: str, n: int = 300) -> str:
    return re.sub(r"\s+", " ", s or "").strip()[:n]


def _numbered_lines(text: str) -> list[str]:
    """Split on \n only (like grep -n and the Read tool), so line numbers cited in claims stay stable; str.splitlines() also
    splits on form feeds and Unicode separators and would shift them."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines
