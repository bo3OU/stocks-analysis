#!/usr/bin/env python3
"""Check that research folders are comparable: same mode (live or as-of) and, for as-of, the same UTC cutoff.

  folders_match.py RESEARCH_DIR PEER_DIR [PEER_DIR ...]

Prints one JSON line {"ok": bool, "mode": ..., "as_of_utc": ..., "problems": [...]}; exit 0 if ok, 1 otherwise. The orchestrator
runs it before delegating; the competition agent runs it on its brief's PEER_DIRS.
"""
import json
import sys
from pathlib import Path


def describe(path: Path) -> dict:
    info = {"path": str(path), "exists": path.is_dir(), "inventory": (path / "INVENTORY.md").is_file(), "mode": "missing", "as_of_utc": None}
    meta = path / "asof.json"
    if meta.is_file() and not meta.is_symlink():
        try:
            info.update(mode="as_of", as_of_utc=json.loads(meta.read_text()).get("as_of_utc"))
        except (ValueError, OSError):
            info["mode"] = "unreadable"
    elif path.is_dir():
        info["mode"] = "as_of_folder_without_asof_json" if "_asof_" in path.name else "live"
    return info


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "problems": ["usage: folders_match.py RESEARCH_DIR [PEER_DIR ...]"]}))
        return 2
    infos = [describe(Path(p).resolve()) for p in sys.argv[1:]]
    ref, problems = infos[0], []
    for i in infos:
        if not i["exists"] or not i["inventory"]:
            problems.append(f"{i['path']}: folder or INVENTORY.md missing")
        if i["mode"] in ("unreadable", "as_of_folder_without_asof_json", "missing"):
            problems.append(f"{i['path']}: mode {i['mode']}")
    for i in infos[1:]:
        if (i["mode"], i["as_of_utc"]) != (ref["mode"], ref["as_of_utc"]):
            problems.append(f"{i['path']}: {i['mode']} {i['as_of_utc']} differs from {ref['mode']} {ref['as_of_utc']}")
    print(json.dumps({"ok": not problems, "mode": ref["mode"], "as_of_utc": ref["as_of_utc"], "problems": problems}))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
