"""Convert SEC filing HTML (incl. inline XBRL) to plain text for reading by agents.

- Drops scripts/styles, the hidden inline-XBRL header (ix:header) and display:none blocks, which otherwise leak
  lines such as 'us-gaap:RevolvingCreditFacilityMember' into the text.
- Table rows become one line with cells joined by ' | ' ('$' cells dropped; '%' and ')' glued to the prior cell).
- PDFs are converted with pdftotext -layout when available.

CLI: python html_to_text.py in.htm out.txt
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def html_bytes_to_text(data: bytes) -> str:
    soup = BeautifulSoup(data, "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    for t in soup.find_all(lambda tag: tag.name and tag.name.lower() == "ix:header"):
        t.decompose()
    for t in soup.find_all(style=re.compile(r"display\s*:\s*none", re.I)):
        t.decompose()
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        merged: list[str] = []
        for c in cells:
            if c in ("", "$"):
                continue
            if c in ("%", ")", "%)") and merged:
                merged[-1] += c
            else:
                merged.append(c)
        tr.replace_with(soup.new_string(" | ".join(merged) + "\n"))
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def convert(src: Path, dst: Path, header: str = "") -> tuple[bool, str]:
    """Return (ok, note). Writes dst with an optional '#'-prefixed header block."""
    suffix = src.suffix.lower()
    try:
        if suffix in (".htm", ".html", ".xhtml"):
            text = html_bytes_to_text(src.read_bytes())
        elif suffix == ".txt":
            text = src.read_text(errors="replace")
        elif suffix == ".pdf":
            if not shutil.which("pdftotext"):
                return False, "pdftotext not installed"
            out = subprocess.run(["pdftotext", "-layout", str(src), "-"], capture_output=True, text=True, timeout=120)
            if out.returncode != 0:
                return False, f"pdftotext failed: {out.stderr[:100]}"
            text = out.stdout
        else:
            return False, f"unsupported type {suffix}"
    except Exception as e:  # noqa: BLE001 - report and continue
        return False, f"{type(e).__name__}: {e}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text((header + "\n" if header else "") + text)
    return True, ""


if __name__ == "__main__":
    ok, note = convert(Path(sys.argv[1]), Path(sys.argv[2]))
    print("ok" if ok else f"failed: {note}")
