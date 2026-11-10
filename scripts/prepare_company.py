"""Phase 1b for the orchestrator: run every deterministic analysis script on a fetched folder, one command.

Runs build_digest, build_insider_ledger, build_tables and positioning_summary (each independent; one failing does not stop the
others) and writes tables/PREPARED.json. peer_table.py needs peer folders and is run separately after folders_match.py.
Usage: .venv/bin/python -I scripts/prepare_company.py <TICKER or RESEARCH_DIR> [--history-years 5]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_HERE = HERE if (HERE / "toolkit.py").is_file() else HERE.parents[2] / "scripts"
sys.path.insert(0, str(SOURCE_HERE))
from toolkit import fail, research_dir, write_atomic  # noqa: E402

STEPS = [("build_digest.py", False), ("build_insider_ledger.py", False), ("build_tables.py", True), ("positioning_summary.py", True),
         ("build_obligations.py", False), ("build_catalysts.py", False), ("proxy_tables.py", False)]


def summarize_output(stdout: str, stderr: str) -> str:
    lines = [line.strip() for line in (stdout + "\n" + stderr).splitlines() if line.strip()]
    diagnostics = [line for line in lines if any(word in line.upper() for word in ("WARN", "ERROR", "TRACEBACK", "EXCLUDED"))]
    chosen = list(dict.fromkeys(diagnostics[:12] + lines[-3:]))
    summary = "\n".join(chosen)
    return summary[:1800] + ("\n... output truncated" if len(summary) > 1800 or len(diagnostics) > 12 else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--history-years", type=int, default=5)
    a = ap.parse_args()
    if a.history_years < 1 or a.history_years > 100:
        fail("--history-years must be between 1 and 100")
    rd = research_dir(a.folder)
    if (rd / "identity.json").is_symlink():
        fail("identity.json is a symlink")
    out = rd / "tables"
    if out.is_symlink() or not out.resolve().is_relative_to(rd):
        fail("tables directory escapes folder")
    results = {}
    for script, takes_years in STEPS:
        path = HERE / script if (HERE / script).is_file() else SOURCE_HERE / script
        cmd = [sys.executable, "-I", str(path), str(rd)] + (["--history-years", str(a.history_years)] if takes_years else [])
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=600)
            output = summarize_output(p.stdout, p.stderr)
            results[script] = {"ok": p.returncode == 0, "output": output}
        except subprocess.TimeoutExpired as exc:
            results[script] = {"ok": False, "output": f"timed out after {exc.timeout}s"}
        except OSError as exc:
            results[script] = {"ok": False, "output": f"could not start: {exc}"}
        print(f"{'OK  ' if results[script]['ok'] else 'FAIL'} {script}: {results[script]['output']}")
    write_atomic(out / "PREPARED.json", json.dumps({"prepared_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "history_years": a.history_years, "steps": results}, indent=1) + "\n")
    sys.exit(0 if all(r["ok"] for r in results.values()) else 1)


if __name__ == "__main__":
    main()
