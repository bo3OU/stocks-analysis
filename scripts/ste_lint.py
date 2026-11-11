"""STE-style lint for brief.md (rules in agents/STYLE_STE.md). Mechanical hints; not a certified ASD-STE100 check.

Checks per sentence: length (more than 20 words = WARN, more than 25 = ERROR); passive voice and perfect/progressive forms (WARN, pattern
based); words from a short non-STE list (WARN); a sentence with a digit and no claim ID like [FIL-041] or [CALC: VAL-007] (ERROR); a claim ID
that does not exist in agents/*/claims.jsonl (ERROR); numbers in a sentence that are not in the cited claim statements (WARN). Per paragraph:
more than 6 sentences (WARN). Per file: more than --max-words words (ERROR). Table rows and headings are checked for claim IDs and numbers only.
Usage: .venv/bin/python -I scripts/ste_lint.py <TICKER or RESEARCH_DIR> [--file brief.md] [--max-words 800]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from toolkit import research_dir, safe_child, write_atomic  # noqa: E402

BAD_WORDS = ["utilize", "utilise", "commence", "terminate", "approximately", "significant", "significantly", "robust", "leverage", "facilitate", "subsequently",
             "furthermore", "additionally", "consequently", "whilst", "endeavor", "in order to", "prior to", "a number of", "substantial"]
PASSIVE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?(?:\w{3,}ed|built|made|done|given|shown|seen|taken|held|sold|bought|paid|run|set|put|found|known|written|driven|brought|raised|cut)\b", re.I)
PERFECT = re.compile(r"\b(?:has|have|had)\s+(?:\w+ly\s+)?(?:\w{3,}ed|been|built|made|done|given|shown|seen|taken|held|sold|bought|paid|run|set|put|found|known|written)\b", re.I)
PROGRESSIVE = re.compile(r"\b(?:is|are|was|were)\s+(?:\w+ly\s+)?\w{3,}ing\b", re.I)
CLAIM_RE = re.compile(r"\[(?:CALC:\s*)?([A-Z]{2,4}-\d{1,4})\]")
SRC_RE = re.compile(r"\[src:\s*([^\]\s:]+)(?::\d+(?:-\d+)?)?\]")  # screen mode: a file inside the research folder instead of a claim ID
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z$\[(\"'])")


def sig(n: str) -> str:
    n = n.replace(",", "").rstrip(".")
    return n.rstrip("0").rstrip(".") if "." in n else n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--file", default="brief.md")
    ap.add_argument("--max-words", type=int, default=800)
    a = ap.parse_args()
    rd = research_dir(a.folder)
    p = safe_child(rd, a.file)
    if p is None or not p.is_file() or p.is_symlink():
        raise SystemExit(f"ERROR: {a.file} not found inside the research folder")
    claims: dict[str, str] = {}
    for cf in sorted((rd / "agents").glob("*/claims.jsonl")):
        if cf.is_symlink():
            continue
        for line in cf.read_text(encoding="utf-8", errors="replace").split("\n"):
            try:
                d = json.loads(line)
                claims[str(d["claim_id"])] = str(d.get("statement", ""))
            except (ValueError, KeyError, TypeError):
                pass
    text = p.read_text(encoding="utf-8", errors="replace")
    findings: list[tuple[str, int, str, str]] = []
    words = len(re.findall(r"\b\w[\w'-]*\b", re.sub(r"\[[^\]]*\]", "", text)))
    if words > a.max_words:
        findings.append(("ERROR", 0, "length", f"{words} words; the limit is {a.max_words}"))
    para_sent = 0
    for ln_no, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line:
            if para_sent > 6:
                findings.append(("WARN", ln_no - 1, "paragraph", f"{para_sent} sentences in one paragraph; the limit is 6"))
            para_sent = 0
            continue
        is_table = line.startswith("|")
        is_head = line.startswith("#")
        body = re.sub(r"^[-*]\s+|^\d+\.\s+", "", line)
        sentences = [body] if is_table or is_head else [s for s in SENT_SPLIT.split(body) if s.strip()]
        if not is_table and not is_head:
            para_sent += len(sentences)
        for s in sentences:
            plain = re.sub(r"\[[^\]]*\]", "", s)
            n_words = len(re.findall(r"\b\w[\w'-]*\b", plain))
            ids = CLAIM_RE.findall(s)
            srcs = SRC_RE.findall(s)
            has_digit = bool(NUM_RE.search(plain)) and not is_head
            if not is_table and not is_head:
                if n_words > 25:
                    findings.append(("ERROR", ln_no, "sentence length", f"{n_words} words: {plain[:70]}..."))
                elif n_words > 20:
                    findings.append(("WARN", ln_no, "sentence length", f"{n_words} words: {plain[:70]}..."))
                for rx, label in ((PASSIVE, "passive voice"), (PERFECT, "perfect tense"), (PROGRESSIVE, "progressive form")):
                    m = rx.search(plain)
                    if m:
                        findings.append(("WARN", ln_no, label, m.group(0)))
                low = plain.lower()
                for w in BAD_WORDS:
                    if re.search(r"\b" + re.escape(w) + r"\b", low):
                        findings.append(("WARN", ln_no, "word", f"'{w}': use a simpler word"))
            for sp in srcs:
                sp_path = safe_child(rd, sp)
                if sp_path is None or not sp_path.is_file():
                    findings.append(("ERROR", ln_no, "unknown source file", sp))
            if has_digit and not ids and not srcs:
                nums = [n for n in NUM_RE.findall(plain) if len(re.sub(r"\D", "", n)) >= 1]
                if nums and not all(re.fullmatch(r"(?:19|20)\d\d|\d{1,2}", n) for n in nums):  # dates, years and small counts are allowed without an ID
                    findings.append(("ERROR", ln_no, "missing claim ID", plain[:80]))
            for cid in ids:
                if cid not in claims:
                    findings.append(("ERROR", ln_no, "unknown claim ID", cid))
            if ids and has_digit:
                support = " ".join(sig(n) for c in ids if c in claims for n in NUM_RE.findall(claims[c]))
                sup = set(support.split())
                miss = [n for n in NUM_RE.findall(plain) if len(re.sub(r"\D", "", n)) >= 3 and sig(n) not in sup]
                if miss and sup:
                    findings.append(("WARN", ln_no, "number not in cited claim", ", ".join(miss[:4])))
    if para_sent > 6:
        findings.append(("WARN", 0, "paragraph", f"{para_sent} sentences in the last paragraph"))
    errs = sum(1 for f in findings if f[0] == "ERROR")
    warns = len(findings) - errs
    out = [f"# STE-style lint: {a.file}", f"{words} words. ERROR {errs}, WARN {warns}. Rules: agents/STYLE_STE.md (a style aid, not a certified ASD-STE100 check).", ""]
    out += [f"- {lvl} line {ln}: {kind}: {detail}" for lvl, ln, kind, detail in findings]
    write_atomic(rd / "tables" / "ste_lint.md", "\n".join(out) + "\n")
    print(f"{words} words; ERROR {errs}, WARN {warns}; details in tables/ste_lint.md")
    for lvl, ln, kind, detail in [f for f in findings if f[0] == "ERROR"][:12]:
        print(f"ERROR line {ln}: {kind}: {detail}")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
