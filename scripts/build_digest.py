"""Filings digest: section index, rule-keyword hit table and a compact digest.md, built from RESEARCH_DIR/text/.

Replaces the filings reader's grep-and-read loop. Outputs (RESEARCH_DIR/digest/): sections.csv, hits.csv, digest.md.
Line numbers are 1-based and match the text files exactly, so claims can cite them and read_section.py can open them.
Usage: .venv/bin/python -I scripts/build_digest.py <TICKER or RESEARCH_DIR>
"""
from __future__ import annotations

import bisect
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if not (Path(__file__).resolve().parent / "toolkit.py").is_file():
    sys.path.insert(1, str(Path(__file__).resolve().parents[3] / "scripts"))
from toolkit import _numbered_lines, clean_cell, fail, read_csv, research_dir, write_atomic, write_csv  # noqa: E402

MAX_HITS_PER_FILE_TOPIC = 6
HEADING_MAX = 200
MAX_TEXT_BYTES = 100_000_000

ITEM_RE = re.compile(r"^\s*ITEM\s+(\d{1,2}(?:\.\d{2})?[A-C]?)\s*[\.\:\-—–]?\s*(.{0,150})$", re.I)
PART_RE = re.compile(r"^\s*PART\s+([IV]{1,3})\b", re.I)
NOTES_START_RE = re.compile(r"^\s*notes?\s+to\s+(?:the\s+)?(?:unaudited\s+)?(?:condensed\s+)?(?:consolidated\s+)?financial\s+statements", re.I)
NOTE_RE = re.compile(r"^\s*(?:[Nn][Oo][Tt][Ee]\s+)?(\d{1,2})\s*[\.\:—–-]\s*([A-Z][A-Za-z0-9 ,&'/\-\(\)]{3,80}?)\s*$")

# (topic, rule id, regex). Review flags only: a hit says "read this passage", never that something is wrong.
TOPICS = [
    ("going_concern", "TXT-A", r"substantial doubt|going concern"),
    ("internal_control", "TXT-A", r"material weakness|not effective|ineffective"),
    ("restatement", "TXT-A", r"restate|non-reliance|previously issued financial statements"),
    ("atm_equity_line", "", r"at[- ]the[- ]market|\bATM (?:offering|program|sales)|sales agreement|equity distribution|equity line"),
    ("shelf_registration", "", r"shelf registration|automatic shelf|Form S-3|prospectus supplement"),
    ("warrants", "", r"pre-funded warrant|warrants? to purchase|exercise price of the warrants"),
    ("convertible_debt", "", r"convertible (?:senior )?notes|conversion (?:price|rate)|capped call"),
    ("debt_facility", "", r"credit agreement|credit facility|term loan|revolving|indenture|financial covenant|maturity date"),
    ("liquidity", "", r"sufficient to fund|ability to continue|raise additional (?:capital|funds)|need to (?:raise|obtain) (?:additional )?(?:capital|funds|financing)"),
    ("plan_10b5_1", "R10B5-B", r"10b5-1"),
    ("change_of_control", "", r"change (?:of|in) control"),
    ("related_party", "", r"related[- ]party|related person"),
    ("legal_dispute", "", r"lawsuit|arbitration|breach of (?:the )?contract|subpoena|complaint (?:was )?filed|injunction"),
    ("customer_concentration", "", r"customers? accounted for|concentration of (?:credit|revenue)|one customer|single customer"),
    ("auditor_change", "E8K-A", r"dismiss(?:ed|al) .{0,60}(?:accounting firm|auditor)|resign(?:ed|ation) .{0,60}(?:accounting firm|auditor)|new independent registered"),
    ("milestone_timing", "", r"we expect to (?:report|complete|initiate|begin|submit|file)|expected to (?:report|complete|read out)|topline (?:data|results)"),
]
TOPIC_RES = [(t, r, re.compile(p, re.I)) for t, r, p in TOPICS]


def parse_header(lines: list[str]) -> dict:
    meta = {"source": "", "form": "", "filed": "", "period": "", "accession": "", "role": ""}
    for ln in lines[:6]:
        if ln.startswith("# SOURCE:"):
            meta["source"] = ln.split(":", 1)[1].strip()
        elif ln.startswith("# FORM:"):
            for part in ln[1:].split("|"):
                k, _, v = part.partition(":")
                k = k.strip().lower()
                if k in ("form", "filed", "period", "accession", "role"):
                    meta[k] = v.strip()
    return meta


def _part_at(lines: list[str], i: int) -> str:
    """Part number if line i (1-based) is a PART heading, also when the converter split it ('PA' / 'RT I')."""
    one = lines[i - 1].strip()
    m = PART_RE.match(one)
    if m and len(one) < 60:
        return m.group(1).upper()
    if i < len(lines) and re.fullmatch(r"P(?:A(?:R(?:T)?)?)?", one, re.I):
        joined = (one + lines[i].strip()).replace(" ", "")
        m = re.fullmatch(r"PART([IV]{1,3})", joined, re.I)
        if m:
            return m.group(1).upper()
    return ""


def find_sections(lines: list[str]) -> list[dict]:
    """Items and ascending numbered notes, excluding converter table-of-contents rows."""
    # A TOC need not contain pipe separators or page numbers. Its first repeated
    # Part/Item pair marks the start of the body, including 10-Q's Part II Item 1.
    toc_cutoff = 0
    toc_start = next((i for i, raw in enumerate(lines[:500], 1)
                      if re.fullmatch(r"\s*table of contents\s*", raw, re.I)), 0)
    if toc_start:
        seen, toc_part = set(), ""
        for i in range(toc_start + 1, len(lines) + 1):
            toc_part = _part_at(lines, i) or toc_part
            m = ITEM_RE.match(lines[i - 1])
            if m:
                key = (toc_part, m.group(1).upper())
                if key in seen:
                    toc_cutoff = i - 1
                    break
                seen.add(key)
    cands, part, notes_on, last_note = [], "", False, 0
    for i, raw in enumerate(lines, 1):
        if len(raw) > HEADING_MAX or i <= 6 and raw.startswith("#"):
            continue
        pt = _part_at(lines, i)
        if pt:
            part = pt
        m = ITEM_RE.match(raw)
        if m:
            if i <= toc_cutoff:
                continue
            title = clean_cell(m.group(2), 100)
            if "|" in title:
                continue
            if i < len(lines) and 0 < len(lines[i].strip()) < 50 and not ITEM_RE.match(lines[i]) and not PART_RE.match(lines[i]) and (not title or lines[i].strip()[:1].islower()):
                nxt = lines[i].strip()
                joiner = " " if not title or nxt.split()[0].lower() in {"and", "or", "of", "for", "to", "in", "on", "with"} else ""
                title = clean_cell(title + joiner + nxt, 100)
            cands.append({"kind": "item", "part": part, "id": m.group(1).upper(), "title": title, "start": i})
            notes_on = False
            continue
        if NOTES_START_RE.match(raw) and len(raw.strip()) < 120:
            notes_on, last_note = True, 0
            continue
        if notes_on:
            nm = NOTE_RE.match(raw)
            if nm and int(nm.group(1)) == last_note + 1:
                last_note += 1
                cands.append({"kind": "note", "part": part, "id": f"N{last_note}", "title": clean_cell(nm.group(2), 100), "start": i})
    groups: dict[tuple, list[dict]] = collections.defaultdict(list)
    for c in cands:
        groups[(c["kind"], c["part"], c["id"])].append(c)
    # A repeated heading inside an item must not replace its true start or make
    # --item ambiguous. TOC rows were removed above, so the first is canonical.
    chosen = [g[0] for g in groups.values()]
    chosen.sort(key=lambda c: c["start"])
    # Notes are nested in a filing Item (usually 10-K Item 8 or 10-Q Item 1).
    # Keep the parent Item open through its notes while each note ends at the
    # next note or Item. A flat next-heading boundary silently omits notes from
    # --item and from the section map's stated Item range.
    next_heading = next_item = len(lines) + 1
    for c in reversed(chosen):
        c["end"] = (next_item if c["kind"] == "item" else next_heading) - 1
        c["lines"] = c["end"] - c["start"] + 1
        next_heading = c["start"]
        if c["kind"] == "item":
            next_item = c["start"]
    return chosen


def find_hits(lines: list[str], sections: list[dict]) -> tuple[list[dict], collections.Counter]:
    starts = [s["start"] for s in sections]
    rows, counts = [], collections.Counter()
    for i, raw in enumerate(lines, 1):
        if i <= 6 and raw.startswith("#"):
            continue
        for topic, rule, rx in TOPIC_RES:
            if rx.search(raw):
                counts[topic] += 1
    wanted = {topic: {1 + round(k * (count - 1) / (min(count, MAX_HITS_PER_FILE_TOPIC) - 1))
                       for k in range(min(count, MAX_HITS_PER_FILE_TOPIC))} if count > 1 else {1}
              for topic, count in counts.items()}
    per = collections.Counter()
    for i, raw in enumerate(lines, 1):
        if i <= 6 and raw.startswith("#"):
            continue
        for topic, rule, rx in TOPIC_RES:
            match = rx.search(raw) if topic in wanted else None
            if match is None:
                continue
            per[topic] += 1
            if per[topic] in wanted[topic]:
                k = bisect.bisect_right(starts, i) - 1
                sec = sections[k] if k >= 0 else None
                label = f"{sec['kind']} {sec['id']}" + (f" (part {sec['part']})" if sec["part"] else "") if sec else ""
                # Long converted lines can put the hit well beyond the first
                # 300 characters. Keep the sampled snippet anchored at the hit.
                offset = max(0, match.start() - 100)
                prefix = "… " if offset else ""
                snippet = prefix + clean_cell(raw[offset:offset + 300 - len(prefix)], 300 - len(prefix))
                rows.append({"topic": topic, "rule_id": rule, "line": i, "section": label, "snippet": snippet})
    return rows, counts


def build(rd: Path) -> dict:
    tdir = rd / "text"
    if tdir.is_symlink():
        fail(f"refusing symlinked text directory: {tdir}")
    if (rd / "digest").is_symlink():
        fail(f"refusing symlinked digest directory: {rd / 'digest'}")
    for name in ("identity.json", "filings_index.csv"):
        if (rd / name).is_symlink():
            fail(f"refusing symlinked input: {rd / name}")
    files = sorted(p for p in tdir.glob("*.txt") if p.is_file() and not p.is_symlink()) if tdir.is_dir() else []
    sec_rows, hit_rows, per_file = [], [], []
    for p in files:
        if p.stat().st_size > MAX_TEXT_BYTES:
            fail(f"text file exceeds {MAX_TEXT_BYTES} bytes: {p.name}")
        lines = _numbered_lines(p.read_text(encoding="utf-8", errors="replace"))
        meta = parse_header(lines)
        secs = find_sections(lines)
        hits, counts = find_hits(lines, secs)
        base = {"file": p.name, "form": meta["form"], "filed": meta["filed"], "period": meta["period"], "accession": meta["accession"]}
        for s in secs:
            sec_rows.append({**base, "kind": s["kind"], "part": s["part"], "id": s["id"], "title": s["title"],
                             "start_line": s["start"], "end_line": s["end"], "lines": s["lines"]})
        for h in hits:
            hit_rows.append({**base, **h})
        per_file.append({**base, "n_lines": len(lines), "sections": secs, "counts": counts})
    out = rd / "digest"
    digest_text = render(rd, per_file)
    write_csv(out / "sections.csv", ["file", "form", "filed", "period", "accession", "kind", "part", "id", "title", "start_line", "end_line", "lines"], sec_rows)
    write_csv(out / "hits.csv", ["file", "form", "filed", "accession", "topic", "rule_id", "line", "section", "snippet"], hit_rows)
    write_atomic(out / "digest.md", digest_text)
    return {"files": len(files), "sections": len(sec_rows), "hits": len(hit_rows)}


def render(rd: Path, per_file: list[dict]) -> str:
    import json
    ident = {}
    try:
        loaded = json.loads((rd / "identity.json").read_text(encoding="utf-8"))
        ident = loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        pass
    o = [f"# Filings digest: {ident.get('ticker', rd.name)} ({ident.get('name', '')})",
         f"Folder {rd.name}; mode {ident.get('mode', '?')}; {len(per_file)} text files. Built by scripts/build_digest.py from `text/` only.",
         "Hits are review flags (a passage to read), not findings. Open passages with `scripts/read_section.py`; line numbers match the text files.", ""]
    by_form = collections.Counter(f["form"] for f in per_file)
    o.append("## Coverage\n" + (", ".join(f"{k} x{v}" for k, v in sorted(by_form.items())) or "none"))
    o.append("\n## 8-K queue (E8K-A; item codes from filings_index.csv, check meaning in the form)")
    index_rows = read_csv(rd / "filings_index.csv")
    text_by_accession = collections.defaultdict(list)
    for f in per_file:
        if f["form"].startswith("8-K"):
            text_by_accession[f["accession"]].append(f["file"])
    q = []
    for r in index_rows:
        if (r.get("form") or "").startswith("8-K"):
            acc = r.get("accessionNumber") or ""
            if acc:
                q.append((r.get("filingDate") or "", acc, r.get("items") or "", r.get("acceptanceDateTime") or "", r.get("primaryDocument") or ""))
    # Keep older folders usable when their index is absent or incomplete.
    indexed = {entry[1] for entry in q}
    for f in per_file:
        if f["form"].startswith("8-K") and f["accession"] not in indexed:
            q.append((f["filed"], f["accession"], "", "", ""))
    seen = set()
    special = []
    for filed, acc, items, acc_dt, primary in sorted(q, reverse=True):
        if acc in seen:
            continue
        seen.add(acc)
        candidates = sorted(text_by_accession.get(acc, []))
        primary_stem = Path(primary).stem.lower()
        preferred = next((name for name in candidates if name.lower().endswith("_" + primary_stem + ".txt")), "") if primary_stem else ""
        files_label = preferred or (", ".join(candidates) if candidates else "text not cached")
        row = f"- {filed} {acc_dt} items [{items or 'UNKNOWN'}] {acc} {files_label}"
        o.append(row)
        if any(code in {"4.01", "4.02"} for code in re.split(r"[,;\s]+", items)):
            special.append(row)
    if not seen:
        o.append("- none in filings_index.csv or text/")
    o.append("\n### Items 4.01 and 4.02 (review separately)")
    o.extend(special or ["- none in indexed 8-K filings"])
    o.append("\n## Hit counts by filing (topic: lines matching; `hits.csv` samples up to %d across each file and topic)" % MAX_HITS_PER_FILE_TOPIC)
    big = [f for f in per_file if f["form"] in ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "10-Q", "10-Q/A", "6-K", "DEF 14A", "424B5", "424B3", "S-3", "S-3ASR", "S-1")]
    for f in sorted(big, key=lambda x: (x["filed"], x["file"]), reverse=True):
        c = ", ".join(f"{t} {n}" for t, n in sorted(f["counts"].items(), key=lambda kv: -kv[1]))
        o.append(f"- {f['filed']} {f['form']} {f['file']}: {c or 'no topic hits'}")
    for role, forms, amendments in (("annual", ("10-K", "20-F", "40-F"), ("10-K/A", "20-F/A", "40-F/A")),
                                    ("interim", ("10-Q",), ("10-Q/A",))):
        latest = sorted((f for f in per_file if f["form"] in forms), key=lambda x: (x["filed"], x["file"]))
        if not latest:
            latest = sorted((f for f in per_file if f["form"] in amendments), key=lambda x: (x["filed"], x["file"]))
        if latest:
            f = latest[-1]
            o.append(f"\n## Section map, latest {role}: {f['file']} ({f['n_lines']} lines)")
            for s in f["sections"]:
                o.append(f"- {s['kind']} {s['id']}{' part ' + s['part'] if s['part'] else ''} {s['title']}: lines {s['start']}-{s['end']}")
            if not f["sections"]:
                o.append("- no recognized item or note headings; use hits.csv and bounded grep")
    foreign = sorted((f for f in per_file if f["form"] == "6-K"), key=lambda x: (x["filed"], x["file"]))
    if foreign:
        f = foreign[-1]
        o.append(f"\n## Latest 6-K (content unclassified): {f['file']} ({f['n_lines']} lines)")
        o.append("A 6-K may be a results report or another furnishing; verify its contents before using it as an interim report.")
        for s in f["sections"]:
            o.append(f"- {s['kind']} {s['id']}{' part ' + s['part'] if s['part'] else ''} {s['title']}: lines {s['start']}-{s['end']}")
    amended = [f for f in per_file if f["form"] in ("10-K/A", "20-F/A", "40-F/A", "10-Q/A", "6-K/A")]
    if amended:
        o.append("\n## Periodic amendments (review their changed passages separately)")
        for f in sorted(amended, key=lambda x: (x["filed"], x["file"]), reverse=True):
            o.append(f"- {f['filed']} {f['form']} period {f['period'] or 'UNKNOWN'} {f['file']}")
    o.append("\n## How to read\n- `read_section.py <folder> <file> --item 7 --part I` or `--lines 100-180` or `--grep REGEX --context 2` (bounded output)\n- `hits.csv` rows give file, line and section; read around them rather than the whole filing.")
    return "\n".join(o) + "\n"


def main():
    if len(sys.argv) != 2:
        fail("usage: build_digest.py <TICKER or RESEARCH_DIR>")
    rd = research_dir(sys.argv[1])
    print(build(rd))


if __name__ == "__main__":
    main()
