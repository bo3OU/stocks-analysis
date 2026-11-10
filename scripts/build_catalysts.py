"""Dated catalyst and obligation candidates from cached filing text: sentences that pair forward-looking wording with a date phrase.

Outputs (RESEARCH_DIR/tables/): catalysts.csv and catalysts.md. Rows are PATTERN HITS (kind is a keyword guess) for an agent to confirm
against the cited lines; the same sentence repeated in several filings is listed once with its first and latest filing.
Usage: .venv/bin/python -I scripts/build_catalysts.py <TICKER or RESEARCH_DIR> [--max-rows 150]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if not (Path(__file__).resolve().parent / "toolkit.py").is_file():
    sys.path.insert(1, str(Path(__file__).resolve().parents[3] / "scripts"))
from build_digest import parse_header  # noqa: E402
from toolkit import _numbered_lines, clean_cell, fail, research_dir, write_atomic, write_csv  # noqa: E402

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_RE = re.compile(r"(Q[1-4]\s?(?:of\s)?20\d\d|(?:first|second|third|fourth) (?:quarter|half) of (?:fiscal )?20\d\d|(?:early|mid|late)[- ](?:to[- ](?:mid|late)[- ])?20\d\d|(?:%s)\s+\d{1,2},\s+20\d\d|(?:by|through|until|in|during|before)(?: the)?(?: end of)?(?: calendar| fiscal)? 20\d\d|(?:%s)\s+20\d\d)" % (MONTHS, MONTHS), re.I)
FORWARD_RE = re.compile(r"\b(expect|anticipate|plan to|plans to|intend|on track|scheduled|will (?:be|begin|complete|report|read|submit|file|expire|mature|become|convert)|expected to|PDUFA|matures?|expires?|expiration|lock-up|due (?:in|on|by)|redeem|redemption)", re.I)
KINDS = [("trial_or_regulatory", r"phase|trial|topline|readout|\b(?:FDA|NDA|BLA|PDUFA|IND)\b|approval|submission|endpoint|dosing"),
         ("financing_or_liquidity", r"cash|runway|fund|offering|notes|convertible|matur|credit|lock-up|dilut|raise|capital|shelf|ATM"),
         ("legal_or_dispute", r"lawsuit|arbitration|hearing|court|complaint|settle|dispute|breach"),
         ("commercial_or_supply", r"launch|manufactur|supply|capacity|customer|contract|commercial|production")]
PERIODIC_OR_EVENT = ("10-K", "10-Q", "8-K", "424B5", "424B3", "S-3", "S-3ASR", "6-K", "20-F", "DEF 14A", "40-F", "S-1")


MONTH_NUM = {m.lower(): i for i, m in enumerate(MONTHS.split("|"), 1)}


def is_future(phrase: str, filed: str) -> bool:
    """Keep a date phrase only when its possible interval reaches the reference filing date."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", filed or "")
    y = re.search(r"(20\d\d)", phrase)
    if not (m and y):
        return False
    try:
        reference = dt.date(*(int(g) for g in m.groups()))
    except ValueError:
        return False
    fy, fm, py = reference.year, reference.month, int(y.group(1))
    if py != fy:
        return py > fy
    # "before 2026" ends as 2026 begins; it is not a future date in a
    # filing made during 2026. "before the end of 2026" remains possible.
    if re.fullmatch(r"before\s+(?:calendar\s+)?20\d\d", phrase, re.I):
        return False
    mon = re.search(MONTHS, phrase, re.I)
    if mon:
        month = MONTH_NUM[mon.group(0).lower()]
        day = re.search(r"\b\d{1,2},\s+20\d\d\b", phrase[mon.end():])
        if day:
            try:
                return dt.date(py, month, int(day.group(0).split(",", 1)[0])) >= reference
            except ValueError:
                return False
        return month >= fm
    # Fiscal quarters and halves cannot be mapped to calendar months without a fiscal year end.
    if re.search(r"\bfiscal\b", phrase, re.I):
        return True
    q = re.search(r"Q([1-4])", phrase, re.I) or re.search(r"(first|second|third|fourth) quarter", phrase, re.I)
    if q:
        n = int(q.group(1)) if q.group(1).isdigit() else ["first", "second", "third", "fourth"].index(q.group(1).lower()) + 1
        return n >= (fm - 1) // 3 + 1
    h = re.search(r"(first|second) half", phrase, re.I)
    if h:
        return (1 if h.group(1).lower() == "first" else 2) >= (1 if fm <= 6 else 2)
    part = re.search(r"\b(early|mid|late)(?:[- ]to[- ](mid|late))?[- ]20\d\d\b", phrase, re.I)
    if part:
        last = (part.group(2) or part.group(1)).lower()
        return fm <= {"early": 4, "mid": 8, "late": 12}[last]
    return True  # a bare current-year phrase ("by the end of 2026") is still ahead


def kind_of(s: str) -> str:
    for k, p in KINDS:
        if re.search(p, s, re.I):
            return k
    return "other"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--max-rows", type=int, default=150)
    a = ap.parse_args()
    if a.max_rows < 0:
        ap.error("--max-rows must be nonnegative")
    rd = research_dir(a.folder)
    tdir = rd / "text"
    seen: dict[str, dict] = {}
    files = [p for p in sorted(tdir.glob("*.txt")) if p.is_file() and not p.is_symlink()] if tdir.is_dir() and not tdir.is_symlink() else []
    filed_dates = []
    for p in files:
        filed = parse_header(p.read_text(encoding="utf-8", errors="replace").split("\n", 6)[:6])["filed"]
        try:
            if not re.fullmatch(r"20\d\d-\d\d-\d\d", filed):
                raise ValueError("invalid filing date")
            dt.date.fromisoformat(filed)
        except ValueError:
            print(f"WARNING: {p.name}: invalid filing date; skipped for catalyst reference date", file=sys.stderr)
            continue
        filed_dates.append(filed)
    if files and not filed_dates:
        fail("no valid filing dates in text files; cannot determine catalyst reference date")
    ref = max(filed_dates, default="")  # newest filing in the folder = "now"
    for p in files:
        lines = _numbered_lines(p.read_text(encoding="utf-8", errors="replace"))
        meta = parse_header(lines)
        if meta["filed"] not in filed_dates:
            continue
        form = meta["form"]
        if (form not in PERIODIC_OR_EVENT and not form.startswith(("10-K/", "10-Q/", "8-K/", "424B", "S-1/", "S-3/", "S-3ASR/", "F-1", "F-3", "6-K/", "20-F/", "40-F/", "DEF 14A/"))):
            continue
        for i, raw in enumerate(lines, 1):
            if (i <= 6 and raw.startswith("#")) or len(raw) < 40 or (" | " in raw and raw.count(" | ") > 3):
                continue
            for sent in re.split(r"(?<=[.;])\s+(?=[A-Z\"(])", raw):
                if len(sent) < 40 or len(sent) > 600:
                    continue
                if not FORWARD_RE.search(sent):
                    continue
                d = next((m for m in DATE_RE.finditer(sent) if is_future(m.group(1), ref)), None)
                if not d:
                    continue
                key = norm(sent)
                row = {"first_filed": meta["filed"], "latest_filed": meta["filed"], "form": meta["form"], "file": p.name, "line": i, "date_phrase": d.group(1),
                       "kind": kind_of(sent), "sentence": clean_cell(sent, 320), "repeats": 1}
                if key in seen:
                    s0 = seen[key]
                    s0["repeats"] += 1
                    if (meta["filed"], p.name, i) >= (s0["latest_filed"], s0["file"], s0["line"]):
                        s0.update({"latest_filed": meta["filed"], "file": p.name, "line": i, "form": meta["form"],
                                   "date_phrase": d.group(1), "kind": kind_of(sent), "sentence": clean_cell(sent, 320)})
                    s0["first_filed"] = min(s0["first_filed"], meta["filed"])
                else:
                    seen[key] = row
    rows = sorted(seen.values(), key=lambda r: (r["latest_filed"], r["file"], r["line"]), reverse=True)
    total = len(rows)
    rows = rows[: a.max_rows]
    out = rd / "tables"
    if out.is_symlink():
        fail(f"refusing to write through a symlink: {out}")
    write_csv(out / "catalysts.csv", ["latest_filed", "first_filed", "form", "kind", "date_phrase", "repeats", "file", "line", "sentence"], rows)
    md = [f"# Catalyst and obligation candidates: {rd.name}", f"Built by scripts/build_catalysts.py: sentences pairing forward-looking wording with a date phrase ({total} found, {len(rows)} shown, newest filings first). Dates are kept only if not earlier than the newest filing in the folder (as of that date). Pattern hits: confirm in the cited lines; a missing item is not proof of absence.", ""]
    for kind in ("trial_or_regulatory", "financing_or_liquidity", "legal_or_dispute", "commercial_or_supply", "other"):
        rs = [r for r in rows if r["kind"] == kind][:25]
        md.append(f"## {kind} ({len([r for r in rows if r['kind'] == kind])})")
        for r in rs:
            md.append(f"- [{r['date_phrase']}] {r['sentence'][:220]} ({r['form']} {r['latest_filed']}, {r['file']}:{r['line']}, seen {r['repeats']}x)")
        md.append("")
    write_atomic(out / "catalysts.md", "\n".join(md) + "\n")
    print({"candidates": total, "shown": len(rows)})


if __name__ == "__main__":
    main()
