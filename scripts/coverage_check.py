"""Coverage check: did the agents' claims touch every filing and event that must not be missed? Mechanical, not a judgment of truth.

Required items (from this folder's own files): every offering/financing filing (424B*, S-1/S-3/F-3, and 8-Ks with items 1.01, 2.03, 3.02),
every 8-K item 4.01, 4.02, 5.02 or 2.04, going-concern / material-weakness / restatement keyword hits in the latest annual and interim report,
the word 'lock-up' wherever an offering document or 8-K uses it, and the insider ledger. An item is covered when a claim cites its file
(source) or accession, or (for keyword items) a claim statement contains the keyword. Output: tables/coverage_check.csv and .md; exit 1 if
anything required is NOT COVERED. Run after the filings reader and again before reconciliation.
Usage: .venv/bin/python -I scripts/coverage_check.py <TICKER or RESEARCH_DIR> [--months 18]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_digest import parse_header  # noqa: E402
from toolkit import _numbered_lines, parse_date, read_csv, research_dir, write_atomic, write_csv  # noqa: E402

OFFERING_FORMS = ("424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "S-1", "S-1/A", "S-3", "S-3ASR", "F-1", "F-3")
FIN_ITEMS = {"1.01", "2.03", "3.02"}
EVENT_ITEMS = {"4.01": "auditor change", "4.02": "non-reliance on financials", "5.02": "executive/director change", "2.04": "acceleration of obligations"}
KEYWORDS = [("going concern", r"substantial doubt|going concern"), ("material weakness", r"material weakness"), ("restatement", r"restate|non-reliance")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--months", type=int, default=18)
    a = ap.parse_args()
    rd = research_dir(a.folder)
    claims = []
    for cf in sorted((rd / "agents").glob("*/claims.jsonl")):
        if cf.is_symlink():
            continue
        for line in cf.read_text(encoding="utf-8", errors="replace").split("\n"):
            try:
                d = json.loads(line)
                if isinstance(d, dict):
                    claims.append(d)
            except ValueError:
                pass
    text_blob = " ".join(f"{c.get('source', '')} {c.get('origin', '')} {c.get('location', '')}" for c in claims).lower()
    statements = " ".join(str(c.get("statement", "")) for c in claims).lower()
    idx = {r["accessionNumber"]: r for r in read_csv(rd / "filings_index.csv")}
    tdir = rd / "text"
    files = [p for p in sorted(tdir.glob("*.txt")) if p.is_file() and not p.is_symlink()] if tdir.is_dir() and not tdir.is_symlink() else []
    meta = {}
    for p in files:
        meta[p] = parse_header(_numbered_lines(p.read_text(encoding="utf-8", errors="replace"))[:8])
    newest = max((parse_date(m["filed"]) for m in meta.values() if parse_date(m["filed"])), default=None)
    cut = (newest - dt.timedelta(days=30 * a.months)) if newest else None
    rows = []

    def add(category, item, covered, detail=""):
        rows.append({"category": category, "item": item, "status": "covered" if covered else "NOT COVERED", "detail": detail})

    def cited(p: Path, accession: str) -> bool:
        return p.name.lower() in text_blob or accession.lower() in text_blob or accession.replace("-", "").lower() in text_blob.replace("-", "")

    for p, m in meta.items():
        filed = parse_date(m["filed"])
        if not filed or (cut and filed < cut):
            continue
        items = {i.strip() for i in (idx.get(m["accession"], {}).get("items") or "").split(",") if i.strip()}
        form = m["form"]
        if form in OFFERING_FORMS or (form.startswith("8-K") and items & FIN_ITEMS):
            add("offering or financing filing", f"{m['filed']} {form} {m['accession']} ({p.name[:60]})", cited(p, m["accession"]), "no claim cites this file or accession")
        for it, label in EVENT_ITEMS.items():
            if form.startswith("8-K") and it in items:
                add(f"8-K item {it} ({label})", f"{m['filed']} {m['accession']} ({p.name[:60]})", cited(p, m["accession"]), "no claim cites this file or accession")
    latest = {}
    for p, m in meta.items():
        role = "annual" if m["form"] in ("10-K", "10-K/A", "20-F", "40-F") else "interim" if m["form"] == "10-Q" else None
        if role and parse_date(m["filed"]) and (role not in latest or parse_date(m["filed"]) > parse_date(latest[role][1]["filed"])):
            latest[role] = (p, m)
    for role, (p, m) in latest.items():
        body = p.read_text(encoding="utf-8", errors="replace")
        for label, pat in KEYWORDS:
            if re.search(pat, body, re.I):
                # a hit may be boilerplate ("no substantial doubt", "no material weakness"): still needs a claim stating the conclusion
                add(f"latest {role} report keyword", f"'{label}' appears in {p.name[:60]}", label in statements or label.replace(" ", "") in statements.replace(" ", ""), f"no claim statement mentions '{label}'")
    lock = [p for p, m in meta.items() if (m["form"] in OFFERING_FORMS or m["form"].startswith("8-K")) and parse_date(m["filed"]) and (not cut or parse_date(m["filed"]) >= cut) and re.search(r"lock-?up", p.read_text(encoding="utf-8", errors="replace"), re.I)]
    if lock:
        add("lock-up", f"'lock-up' appears in {len(lock)} recent offering/8-K files (newest {lock[-1].name[:60]})", bool(re.search(r"lock-?up", statements)), "no claim statement mentions the lock-up")
    ledger = rd / "digest" / "insider_ledger.csv"
    if ledger.is_file() and len(read_csv(ledger)) > 0:
        add("insider activity", f"{len(read_csv(ledger))} Form 3/4/5 transaction rows in digest/insider_ledger.csv", any(w in text_blob + statements for w in ("insider_ledger", "insider_filings", "form 4", "form4", "insider")), "no claim cites or mentions the insider ledger")
    missing = [r for r in rows if r["status"] != "covered"]
    write_csv(rd / "tables" / "coverage_check.csv", ["category", "item", "status", "detail"], rows)
    md = [f"# Coverage check: {rd.name}", f"{len(rows)} required items from filings dated within {a.months} months of the newest filing; {len(missing)} NOT COVERED. Mechanical: a claim citing a file counts as coverage, not as proof the claim is right.", ""]
    md += [f"- NOT COVERED [{r['category']}] {r['item']}: {r['detail']}" for r in missing] or ["- all required items are cited by at least one claim"]
    write_atomic(rd / "tables" / "coverage_check.md", "\n".join(md) + "\n")
    print(f"{len(rows)} required items, {len(missing)} NOT COVERED; see tables/coverage_check.md")
    for r in missing[:15]:
        print(f"NOT COVERED [{r['category']}] {r['item']}")
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
