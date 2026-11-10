#!/usr/bin/env python3
"""Split skills.md into skills/<name>/SKILL.md (one-way: edit skills.md, re-run this). Agents read these files directly;
the user can also copy skills/* into ~/.claude/skills/ later."""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
text = (root / "skills.md").read_text()
blocks = re.findall(r"````markdown\n(.*?)\n````", text, flags=re.S)
out = root / "skills"
out.mkdir(exist_ok=True)
names = []
for b in blocks:
    m = re.search(r"^name: (\S+)$", b, flags=re.M)
    if not m:
        sys.exit("block without a name: " + b[:80])
    d = out / m.group(1)
    d.mkdir(exist_ok=True)
    (d / "SKILL.md").write_text(b + "\n")
    names.append(m.group(1))
print(f"{len(names)} skills written to {out}: {', '.join(names)}")
