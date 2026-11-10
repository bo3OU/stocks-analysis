"""Digest an earnings-call transcript (plain text already saved inside a research folder): speaker turns, prepared remarks vs Q&A,
guidance-like sentences and number mentions, with line numbers. No fetching; the agent saves the page text (html_to_text.py output)
under RESEARCH_DIR first.
Outputs next to the input: <name>.digest.md and <name>.turns.csv (turn, section, speaker, first_line, last_line, words).
Usage: .venv/bin/python -I scripts/parse_transcript.py <TICKER or RESEARCH_DIR> <relative path to transcript .txt> [--max-guidance 60]
"""
from __future__ import annotations

import argparse
import bisect
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_HERE = HERE if (HERE / "toolkit.py").is_file() else HERE.parents[2] / "scripts"
sys.path.insert(0, str(SOURCE_HERE))
from toolkit import _numbered_lines, clean_cell, fail, research_dir, safe_child, write_atomic, write_csv  # noqa: E402

# A dash separates a speaker only when surrounded by spaces. Otherwise the
# first word of a sentence such as "Forward-looking statements ..." becomes
# a spurious speaker named "Forward".
SPEAKER_RE = re.compile(r"^\s*([A-Z][A-Za-z.\-'’]+(?:\s+[A-Z][A-Za-z.\-'’]+){0,3})(?::|\s+[-–—]\s+|\s+\(([^)]{2,60})\))\s*(.*)$")
QA_RE = re.compile(r"first question|open (?:the )?(?:line|call) for questions|begin the question", re.I)
GUIDE_RE = re.compile(r"\b(guidance|outlook|we expect|we anticipate|expect(?:s|ed)? (?:to|that|revenue|growth)|target|on track|range of|between \$?\d|forecast|plan to|will (?:be|begin|report|launch))\b", re.I)
NUM_RE = re.compile(r"\$\s?\d[\d,.]*(?:\s?(?:million|billion|M|B))?|\b\d{1,3}(?:\.\d+)?\s?%")
NOT_SPEAKERS = {"Q", "A"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("path", help="transcript text file, relative to the research folder")
    ap.add_argument("--max-guidance", type=int, default=60)
    a = ap.parse_args()
    if a.max_guidance < 0:
        fail("--max-guidance must be nonnegative")
    rd = research_dir(a.folder)
    p = safe_child(rd, a.path)
    if p is None or not p.is_file() or p.is_symlink() or p.suffix.lower() != ".txt":
        fail("transcript must be an existing .txt file inside the research folder")
    lines = _numbered_lines(p.read_text(encoding="utf-8", errors="replace"))
    ROLE_RE = re.compile(r"\b(CEO|CFO|COO|CMO|CSO|President|Officer|Analyst|Director|Relations|Chief|Vice|VP|Partner|Managing|Head|Founder|Chair|Research|Equity)\b")
    NAME_RE = re.compile(r"^[A-Z][A-Za-z.\-'’]+(?: [A-Z][A-Za-z.\-'’]+){0,3}\??$")
    stripped = [ln.strip() for ln in lines]
    counts: dict = {}
    for ln in stripped:
        if NAME_RE.match(ln) and len(ln) <= 40:
            counts[ln] = counts.get(ln, 0) + 1
    speakers = set()
    for k, ln in enumerate(stripped[:-1]):
        if NAME_RE.match(ln) and len(ln) <= 40 and (ln == "Operator" or len(ln.split()) >= 2 and not ln.endswith(".")) and (ln == "Operator" or counts[ln] >= 2 or (ROLE_RE.search(stripped[k + 1]) and len(stripped[k + 1]) <= 120 and "," in stripped[k + 1])):
            speakers.add(ln)
    start = next((i for i, ln in enumerate(stripped) if ln == "Full Transcript"), 0)  # skip page chrome before the transcript when the layout has this marker
    section, turns, cur = "prepared", [], None
    for i, raw in enumerate(lines, 1):
        if i <= start or not raw.strip():
            continue
        name, inline = None, ""
        if speakers and raw.strip() in speakers:
            name = raw.strip()
        else:  # Some saved pages mix standalone headings with "Name: text" turns.
            m = SPEAKER_RE.match(raw)
            if m and len(m.group(1).split()) <= 4 and m.group(1) not in NOT_SPEAKERS | {"Page", "Source"}:
                name = m.group(1)
                inline = m.group(3).strip()
        # Narrative about a future question is not itself the start of Q&A.
        if QA_RE.search(raw) and len(raw) < 200 and section == "prepared" and i > 5 and (name == "Operator" or (cur and cur["speaker"].split(" (", 1)[0] == "Operator")):
            section = "qa"
        if name:
            if cur:
                turns.append(cur)
            cur = {"section": section, "speaker": name, "first_line": i, "last_line": i,
                   "words": len(inline.split()), "text": [inline] if inline else [],
                   "text_lines": [i] if inline else []}
        elif cur:
            if len(cur["text"]) == 0 and cur["words"] == 0 and ROLE_RE.search(raw) and len(raw) <= 120 and "," in raw:
                cur["speaker"] += f" ({raw.strip()})"
                if re.search(r"\bAnalyst\b", raw):  # the first analyst's turn starts Q&A
                    section = cur["section"] = "qa"
            else:
                cur["words"] += len(raw.split())
                cur["text"].append(raw)
                cur["text_lines"].append(i)
            cur["last_line"] = i
    if cur:
        turns.append(cur)
    if not turns:
        fail("no speaker turns recognised; the page text may need a different format (check the file and report the layout)")
    guide = []
    for t in turns:
        starts, offset = [], 0
        for part in t["text"]:
            starts.append(offset)
            offset += len(part) + 1
        joined = " ".join(t["text"])
        for match in re.finditer(r".+?(?:(?<=[.!?])\s+|\Z)", joined, re.S):
            sent = match.group().strip()
            if GUIDE_RE.search(sent) and NUM_RE.search(sent):
                first_char = match.start() + len(match.group()) - len(match.group().lstrip())
                ln = t["text_lines"][bisect.bisect_right(starts, first_char) - 1]
                guide.append((ln, t["speaker"], t["section"], clean_cell(sent, 300)))
    out = p.with_suffix("")
    write_csv(Path(str(out) + ".turns.csv"), ["turn", "section", "speaker", "first_line", "last_line", "words"],
              [{"turn": k, "section": t["section"], "speaker": t["speaker"], "first_line": t["first_line"], "last_line": t["last_line"], "words": t["words"]} for k, t in enumerate(turns, 1)])
    by_sp: dict = {}
    for t in turns:
        by_sp.setdefault((t["speaker"], t["section"]), 0)
        by_sp[(t["speaker"], t["section"])] += t["words"]
    md = [f"# Transcript digest: {p.name}", f"{len(turns)} speaker turns; prepared-remarks turns {sum(t['section'] == 'prepared' for t in turns)}, Q&A turns {sum(t['section'] == 'qa' for t in turns)}. Pattern-based: confirm in the cited lines.", "", "## Words by speaker and section"]
    md += [f"- {s} [{sec}]: {w}" for (s, sec), w in sorted(by_sp.items(), key=lambda kv: -kv[1])[:20]]
    md += ["", f"## Guidance-like sentences with numbers ({len(guide)}; first {a.max_guidance})"]
    md += [f"- line {ln} {sp} [{sec}]: {s}" for ln, sp, sec, s in guide[: a.max_guidance]]
    write_atomic(Path(str(out) + ".digest.md"), "\n".join(md) + "\n")
    print({"turns": len(turns), "guidance_sentences": len(guide)})


if __name__ == "__main__":
    main()
