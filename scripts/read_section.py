"""Bounded reader for cached filing text: a line range, a section, or regex matches with context.

Usage (output lines are `<line number><TAB><text>`, 1-based like the text files):
  read_section.py <folder> <file in text/> --lines 100-180
  read_section.py <folder> <file> --item 7 [--part I]     (or --item 1A, --note 7 -> sections found by build_digest)
  read_section.py <folder> <file> --grep 'regex' [--context 2] [--max-matches 20]
Output is capped by --max-lines (default 250) and says when it truncated.
"""
from __future__ import annotations

import argparse
import re
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if not (Path(__file__).resolve().parent / "toolkit.py").is_file():
    sys.path.insert(1, str(Path(__file__).resolve().parents[3] / "scripts"))
from build_digest import find_sections  # noqa: E402
from toolkit import _numbered_lines, fail, research_dir, safe_child  # noqa: E402

MAX_OUTPUT_CHARS_PER_LINE = 4000
GREP_TIMEOUT_SECONDS = 10
MAX_TEXT_BYTES = 100_000_000


def _grep_timeout(_signum, _frame):
    raise TimeoutError("regex search exceeded time limit")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("file", help="file name inside <folder>/text/")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--lines")
    g.add_argument("--item")
    g.add_argument("--note")
    g.add_argument("--grep")
    ap.add_argument("--part", default="")
    ap.add_argument("--context", type=int, default=1)
    ap.add_argument("--max-lines", type=int, default=250)
    ap.add_argument("--max-matches", type=int, default=20)
    a = ap.parse_args()
    if a.context < 0 or a.max_lines < 1 or a.max_matches < 1:
        fail("--context must be nonnegative; --max-lines and --max-matches must be positive")
    if (a.item is not None and not a.item.strip()) or (a.note is not None and not a.note.strip()):
        fail("--item and --note require a nonempty identifier")
    rd = research_dir(a.folder)
    tdir = rd / "text"
    if tdir.is_symlink():
        fail(f"refusing symlinked text directory: {tdir}")
    candidate = tdir / a.file
    p = safe_child(tdir, a.file)
    if p is None or p.parent != tdir.resolve() or candidate.is_symlink() or not p.is_file():
        fail(f"no such file in text/: {a.file}")
    if p.stat().st_size > MAX_TEXT_BYTES:
        fail(f"text file exceeds {MAX_TEXT_BYTES} bytes: {a.file}")
    lines = _numbered_lines(p.read_text(encoding="utf-8", errors="replace"))
    n = len(lines)
    ranges: list[tuple[int, int]] = []
    grep_offsets: dict[int, int] = {}
    if a.lines:
        m = re.fullmatch(r"(\d{1,9})(?:-(\d{1,9}))?", a.lines.strip())
        if not m:
            fail("--lines needs A-B")
        s, e = int(m.group(1)), int(m.group(2) or m.group(1))
        if s < 1 or e < s or s > n:
            fail("invalid line range")
        ranges.append((s, min(e, n)))
    elif a.item or a.note:
        kind, want = ("item", a.item.strip().upper()) if a.item is not None else ("note", "N" + a.note.strip().upper().lstrip("N"))
        secs = [s for s in find_sections(lines) if s["kind"] == kind and s["id"] == want and (not a.part or s["part"] == a.part.upper())]
        if not secs:
            fail(f"no {kind} {want} found; see digest/sections.csv")
        if len(secs) > 1:
            fail(f"{kind} {want} is ambiguous (parts {', '.join(s['part'] or '-' for s in secs)}); add --part")
        ranges.append((secs[0]["start"], secs[0]["end"]))
    else:
        if len(a.grep) > 300:
            fail("--grep pattern exceeds 300 characters")
        try:
            rx = re.compile(a.grep, re.I)
        except re.error as e:
            fail(f"bad regex: {e}")
        total = 0
        old_handler = signal.signal(signal.SIGALRM, _grep_timeout)
        signal.setitimer(signal.ITIMER_REAL, GREP_TIMEOUT_SECONDS)
        try:
            for i, ln in enumerate(lines, 1):
                match = rx.search(ln)
                if match is None:
                    continue
                total += 1
                if total <= a.max_matches:
                    grep_offsets[i] = match.start()
                    lo, hi = max(1, i - a.context), min(n, i + a.context)
                    if ranges and lo <= ranges[-1][1] + 1:
                        ranges[-1] = (ranges[-1][0], max(ranges[-1][1], hi))
                    else:
                        ranges.append((lo, hi))
        except TimeoutError:
            fail(f"--grep exceeded {GREP_TIMEOUT_SECONDS} seconds; use a simpler pattern or --lines")
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
        print(f"# {total} matching lines in {a.file}; showing {min(total, a.max_matches)}", file=sys.stderr)
    printed = 0
    for lo, hi in ranges:
        if len(ranges) > 1:
            print(f"--- lines {lo}-{hi}")
        for i in range(lo, hi + 1):
            if printed >= a.max_lines:
                print(f"# truncated at {a.max_lines} lines; continue with --lines {i}-{hi}")
                return
            line = lines[i - 1]
            if len(line) > MAX_OUTPUT_CHARS_PER_LINE:
                # A converter can put a whole table or paragraph on one line.
                # In grep mode show the matching text even if it starts beyond
                # the default prefix; retain the original 1-based line number.
                start = max(0, min(grep_offsets.get(i, 0) - 1000, len(line) - MAX_OUTPUT_CHARS_PER_LINE))
                excerpt = line[start:start + MAX_OUTPUT_CHARS_PER_LINE]
                if start:
                    line = f"[characters {start + 1}-{start + len(excerpt)} of {len(line)}] {excerpt} [line truncated]"
                else:
                    line = excerpt + f" [line truncated at {MAX_OUTPUT_CHARS_PER_LINE} characters]"
            print(f"{i}\t{line}")
            printed += 1


if __name__ == "__main__":
    main()
