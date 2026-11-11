"""Per-agent cost ledger for headless runs (`claude -p ... --output-format stream-json --verbose`).

  cost_ledger.py stamp            stdin -> stdout filter that adds the arrival time (_t, epoch seconds) to every JSON line; put it between
                                  claude and the log file so wall time per agent can be measured:  claude ... | cost_ledger.py stamp > run.jsonl
  cost_ledger.py report FILE...   per agent: model, turns, tool calls, tool-output tokens (chars/4), input/cache-read/cache-write tokens, wall time
                                  (first to last message; needs stamped lines), plus the run's reported total cost.
Token counts come from the usage blocks in the stream (output tokens in streamed messages are incomplete, so they are not reported). The
reported cost is the CLI's API-price estimate, not a bill. Usage:  .venv/bin/python -I scripts/cost_ledger.py report run.jsonl
"""
from __future__ import annotations

import collections
import json
import sys
import time


def stamp():
    for line in sys.stdin:
        line = line.rstrip("\n")
        if line.startswith("{"):
            try:
                d = json.loads(line)
                d["_t"] = time.time()
                line = json.dumps(d)
            except ValueError:
                pass
        print(line, flush=True)


def report(files: list[str]):
    spawn: dict[str, str] = {}
    msgs = []
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            msgs += [json.loads(l) for l in fh if l.startswith("{")]
    for e in msgs:
        if e.get("type") == "assistant":
            for c in e["message"]["content"]:
                if c["type"] == "tool_use" and c["name"] in ("Agent", "Task"):
                    spawn[c["id"]] = c["input"].get("subagent_type") or "agent"
    stat = collections.defaultdict(lambda: collections.Counter())
    seen, first, last, models, uses = set(), {}, {}, {}, {}
    total_cost = None
    for e in msgs:
        t = e.get("type")
        if t == "result":
            total_cost = e.get("total_cost_usd", total_cost)
        par = e.get("parent_tool_use_id")
        who = spawn.get(par, "subagent") if par else "main session"
        if "_t" in e:
            first.setdefault(who, e["_t"])
            last[who] = e["_t"]
        if t == "assistant":
            m = e["message"]
            models[who] = m.get("model", models.get(who, ""))
            for c in m["content"]:
                if c["type"] == "tool_use":
                    uses[c["id"]] = who
                    stat[who]["calls"] += 1
            u = m.get("usage") or {}
            if m.get("id") and m["id"] not in seen:
                seen.add(m["id"])
                s = stat[who]
                s["turns"] += 1
                s["in"] += u.get("input_tokens", 0)
                s["cr"] += u.get("cache_read_input_tokens", 0)
                s["cw"] += u.get("cache_creation_input_tokens", 0)
        elif t == "user" and isinstance(e["message"].get("content"), list):
            for c in e["message"]["content"]:
                if c.get("type") == "tool_result" and c["tool_use_id"] in uses:
                    body = c.get("content")
                    body = "\n".join(x.get("text", "") for x in body if isinstance(x, dict)) if isinstance(body, list) else str(body)
                    stat[uses[c["tool_use_id"]]]["out_chars"] += len(body)
    print(f"{'agent':28s}{'model':20s}{'turns':>6s}{'calls':>6s}{'tool-out K tok':>15s}{'cache-read M':>13s}{'cache-write M':>14s}{'wall min':>9s}")
    tot = collections.Counter()
    for who, s in sorted(stat.items(), key=lambda kv: -kv[1]["cr"]):
        wall = f"{(last[who] - first[who]) / 60:.1f}" if who in first and who in last else "n/a"
        print(f"{who:28s}{models.get(who, '')[:19]:20s}{s['turns']:6d}{s['calls']:6d}{s['out_chars'] / 4000:15.0f}{s['cr'] / 1e6:13.1f}{s['cw'] / 1e6:14.2f}{wall:>9s}")
        tot.update(s)
    print(f"{'TOTAL':28s}{'':20s}{tot['turns']:6d}{tot['calls']:6d}{tot['out_chars'] / 4000:15.0f}{tot['cr'] / 1e6:13.1f}{tot['cw'] / 1e6:14.2f}")
    if first:
        print(f"run wall time: {(max(last.values()) - min(first.values())) / 60:.1f} min")
    print(f"CLI-reported total cost (API-price estimate): {total_cost if total_cost is not None else 'n/a (run not finished)'}")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "stamp":
        stamp()
    elif len(sys.argv) >= 3 and sys.argv[1] == "report":
        report(sys.argv[2:])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
