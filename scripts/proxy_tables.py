"""Raw table rows from proxy statements (DEF 14A / DEFA14A) already converted to text: summary compensation, security ownership, and
director/officer lines, with line numbers. No interpretation: rows are split on ' | ' as html_to_text.py writes table cells.
Outputs (RESEARCH_DIR/tables/): proxy_tables.csv (file, filed, table, line, c1..c14) and proxy_tables.md (counts and the first rows).
Usage: .venv/bin/python -I scripts/proxy_tables.py <TICKER or RESEARCH_DIR> [--max-rows 80]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if not (Path(__file__).resolve().parent / "toolkit.py").is_file():
    sys.path.insert(1, str(Path(__file__).resolve().parents[3] / "scripts"))
from build_digest import parse_header  # noqa: E402
from toolkit import _numbered_lines, clean_cell, fail, research_dir, write_atomic, write_csv  # noqa: E402

TABLES = [("summary_compensation", re.compile(r"^\s*(?:\d{4}\s+)?summary compensation\b", re.I)),
          ("security_ownership", re.compile(r"security ownership of certain beneficial owners|beneficial ownership of (?:our )?common stock", re.I)),
          ("outstanding_equity_awards", re.compile(r"\boutstanding equity awards\b", re.I)),
          ("director_compensation", re.compile(r"\b(?:non-employee\s+)?director compensation\b", re.I)),
          ("pay_versus_performance", re.compile(r"^\s*pay versus performance\b", re.I))]
MAX_COLS = 14
WINDOW = 600
MAX_GAP = 8


def table_line_numbers(lines: list[str], heading: int) -> list[int]:
    """Collect one local table block, stopping before a later section or table."""
    found: list[int] = []
    gap = 0
    for i in range(heading + 1, min(heading + WINDOW, len(lines)) + 1):
        ln = lines[i - 1]
        # Converted two-column tables have just one separator.
        if " | " in ln and sum(bool(c.strip()) for c in ln.split(" | ")) >= 2:
            found.append(i)
            gap = 0
            continue
        if len(ln) < 160 and any(rx.search(ln) for _, rx in TABLES):
            break
        if found:
            gap += 1
            if gap >= MAX_GAP:
                break
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--max-rows", type=int, default=80)
    a = ap.parse_args()
    if a.max_rows < 0:
        ap.error("--max-rows must be nonnegative")
    rd = research_dir(a.folder)
    tdir = rd / "text"
    rows = []
    files = sorted(p for p in tdir.glob("*.txt") if p.is_file() and not p.is_symlink()) if tdir.is_dir() and not tdir.is_symlink() else []
    for p in files:
        lines = _numbered_lines(p.read_text(encoding="utf-8", errors="replace"))
        meta = parse_header(lines)
        if not meta["form"].startswith(("DEF 14A", "DEFA14A", "DEFM14A", "PRE 14A")):
            continue
        for name, rx in TABLES:
            hits = [i for i, ln in enumerate(lines, 1) if rx.search(ln) and len(ln) < 160 and " | " not in ln]
            best, best_lines = None, []
            for h in hits:  # the heading followed by the most table rows is the real table, not a table-of-contents or text mention
                found = table_line_numbers(lines, h)
                if len(found) > len(best_lines):
                    best, best_lines = h, found
            if best is None:
                continue
            if best_lines and best_lines[-1] >= best + WINDOW and best + WINDOW < len(lines):
                print(f"WARNING: {p.name} {name}: table may continue beyond {WINDOW} lines after heading", file=sys.stderr)
            warned = False
            warned_cell = False
            for i in best_lines:
                ln = lines[i - 1]
                raw_cells = ln.split(" | ")
                if len(raw_cells) > MAX_COLS and not warned:
                    print(f"WARNING: {p.name} {name} has more than {MAX_COLS} cells; see source lines", file=sys.stderr)
                    warned = True
                if any(len(clean_cell(c, 81)) > 80 for c in raw_cells[:MAX_COLS]) and not warned_cell:
                    print(f"WARNING: {p.name} {name} has cells longer than 80 characters; see source lines", file=sys.stderr)
                    warned_cell = True
                cells = [clean_cell(c, 80) for c in raw_cells[:MAX_COLS]]
                rows.append({"file": p.name, "filed": meta["filed"], "table": name, "line": i, **{f"c{k}": c for k, c in enumerate(cells, 1)}})
    cols = ["file", "filed", "table", "line"] + [f"c{k}" for k in range(1, MAX_COLS + 1)]
    out = rd / "tables"
    if out.is_symlink():
        fail(f"refusing to write through a symlink: {out}")
    write_csv(out / "proxy_tables.csv", cols, rows)
    md = [f"# Proxy table rows: {rd.name}", "Built by scripts/proxy_tables.py: raw cells from the text conversion (column meaning must be read from the header row; confirm numbers in the cited lines).", ""]
    for name, _ in TABLES:
        rs = sorted((r for r in rows if r["table"] == name), key=lambda r: (r["filed"], r["file"]), reverse=True)
        md.append(f"## {name} ({len(rs)} rows)")
        for r in rs[: a.max_rows // 5]:
            md.append(f"- {r['filed']} line {r['line']}: " + " | ".join(r.get(f"c{k}", "") for k in range(1, 9) if r.get(f"c{k}", "")))
        md.append("")
    write_atomic(out / "proxy_tables.md", "\n".join(md) + "\n")
    print({"rows": len(rows), "proxy_files": len({r['file'] for r in rows})})


if __name__ == "__main__":
    main()
