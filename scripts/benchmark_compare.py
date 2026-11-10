"""Relative performance of a company against a benchmark (sector ETF or index) from two cached Finviz daily price files.

The benchmark folder is fetched first, at the same cutoff as the company: `fetch_company.py XBI --only finviz` (then this script).
Outputs (TARGET RESEARCH_DIR/tables/): benchmark_<BENCH>.csv (daily aligned returns not stored; windows summary) and benchmark_<BENCH>.md.
Metrics: aligned trading days, correlation and beta of daily returns (full window and last 252 days), relative price return over
1m/3m/6m/1y (target minus benchmark, percentage points), maximum drawdown of each. Price returns only; split-adjusted as retrieved.
Usage: .venv/bin/python -I scripts/benchmark_compare.py <TARGET> <BENCH_FOLDER> [--history-years 5]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if not (HERE / "toolkit.py").is_file():
    sys.path.insert(1, str(HERE.parents[2] / "scripts"))
from toolkit import fail, num, parse_date, read_csv, research_dir, safe_child, write_atomic, write_csv  # noqa: E402


def series(rd: Path) -> dict[dt.date, float]:
    f = rd / "raw" / "finviz" / "price_history_daily.csv"
    if safe_child(rd, "raw/finviz/price_history_daily.csv") is None:
        fail(f"price history path escapes research folder: {f}")
    out, conflict, bad = {}, set(), 0
    for r in read_csv(f):
        # DictReader fills missing trailing columns with None and puts extra
        # columns under a None key. Either can shift volume into Close.
        if None in r or any(value is None for value in r.values()):
            bad += 1
            continue
        d, c = parse_date(r.get("Date")), num(r.get("Close"))
        if not d or c is None or not math.isfinite(c) or c <= 0:
            bad += 1
            continue
        if d in out and abs(out[d] - c) > 1e-9:
            conflict.add(d)
        out[d] = c
    for d in conflict:  # conflicting duplicate rows: excluded, not guessed
        out.pop(d, None)
    if bad:
        print(f"WARNING: {rd.name}: {bad} price rows with missing, invalid or nonpositive date/close excluded", file=sys.stderr)
    if conflict:
        print(f"WARNING: {rd.name}: {len(conflict)} dates with conflicting closes excluded", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("bench")
    ap.add_argument("--history-years", type=int, default=5)
    a = ap.parse_args()
    if not 1 <= a.history_years <= 100:
        fail("--history-years must be 1..100")
    t_rd, b_rd = research_dir(a.target), research_dir(a.bench)
    if safe_child(t_rd, "tables") is None:
        fail("tables path escapes target research folder")
    identities = []
    for rd in (t_rd, b_rd):
        if safe_child(rd, "identity.json") is None:
            fail(f"identity path escapes research folder: {rd}")
        try:
            ident = json.loads((rd / "identity.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            fail(f"cannot read {rd.name}/identity.json: {e}")
        if not isinstance(ident, dict) or ident.get("mode") not in ("live", "as_of"):
            fail(f"{rd.name}/identity.json needs mode live or as_of")
        if ident["mode"] == "as_of" and not isinstance(ident.get("as_of_utc"), str):
            fail(f"{rd.name}/identity.json needs as_of_utc for as-of mode")
        if ident["mode"] == "as_of" and not ident["as_of_utc"].strip():
            fail(f"{rd.name}/identity.json has empty as_of_utc")
        identities.append(ident)
    ti, bi = identities
    if ti.get("mode") != bi.get("mode"):
        fail("target and benchmark folders mix live and as-of modes")
    if ti.get("mode") == "as_of" and ti.get("as_of_utc") != bi.get("as_of_utc"):
        fail("target and benchmark were cut at different instants")
    ts, bs = series(t_rd), series(b_rd)
    common = sorted(set(ts) & set(bs))
    if len(common) < 60:
        fail("fewer than 60 aligned trading days")
    last = common[-1]
    try:
        first = last.replace(year=last.year - a.history_years)
    except ValueError:  # February 29 in a non-leap lookback year
        first = last.replace(year=last.year - a.history_years, day=28)
    common = [d for d in common if d >= first]
    if len(common) < 60:
        fail("fewer than 60 aligned trading days in the selected history window")
    # A return is one observed trading interval in both files; do not join across an unaligned trading date.
    t_pos = {d: i for i, d in enumerate(sorted(ts))}
    b_pos = {d: i for i, d in enumerate(sorted(bs))}
    pairs = [(ts[b] / ts[a_] - 1, bs[b] / bs[a_] - 1) for a_, b in zip(common, common[1:])
             if (b - a_).days <= 5 and t_pos[b] == t_pos[a_] + 1 and b_pos[b] == b_pos[a_] + 1]
    skipped = len(common) - 1 - len(pairs)
    if skipped:
        print(f"WARNING: {skipped} return intervals spanning price-history gaps or unaligned trading dates excluded", file=sys.stderr)
    if len(pairs) < 30 or not all(math.isfinite(x) and math.isfinite(y) for x, y in pairs):
        fail("fewer than 30 valid aligned daily returns or return overflow")

    def beta_corr(ps):
        if len(ps) < 30:
            return None, None
        x, y = [p[1] for p in ps], [p[0] for p in ps]
        vx = statistics.pvariance(x)
        if vx == 0:
            return None, None
        mx, my = statistics.fmean(x), statistics.fmean(y)
        cov = statistics.fmean([(a_ - mx) * (b - my) for a_, b in zip(x, y)])
        vy = statistics.pvariance(y)
        return cov / vx, (cov / math.sqrt(vx * vy) if vy else None)

    rows = []
    for label, ps in (("full window", pairs), ("last 252 daily returns", pairs[-252:])):
        b, c = beta_corr(ps)
        rows.append({"metric": f"beta vs {b_rd.name} ({label})", "value": "" if b is None else f"{b:.2f}", "basis": f"{len(ps)} daily price returns"})
        rows.append({"metric": f"correlation vs {b_rd.name} ({label})", "value": "" if c is None else f"{c:.2f}", "basis": ""})
    for lbl, days in (("1m", 30), ("3m", 91), ("6m", 182), ("1y", 365)):
        ref = max((d for d in common if d <= last - dt.timedelta(days=days)), default=None)
        if ref and (last - ref).days <= days + 7:
            tr, br = ts[last] / ts[ref] - 1, bs[last] / bs[ref] - 1
            if not math.isfinite(tr) or not math.isfinite(br):
                fail(f"relative return overflowed for {lbl}")
            rows.append({"metric": f"relative_return_{lbl} (target minus benchmark)", "value": f"{(tr - br) * 100:+.1f} pp", "basis": f"target {tr * 100:.1f}%, benchmark {br * 100:.1f}% from {ref} to {last}"})
        else:
            print(f"WARNING: no aligned close near the {lbl} lookback; relative return omitted", file=sys.stderr)
    for name, ser in ((t_rd.name, ts), (b_rd.name, bs)):
        peak, mdd = 0.0, 0.0
        for d in common:
            peak = max(peak, ser[d])
            mdd = min(mdd, ser[d] / peak - 1)
        rows.append({"metric": f"max_drawdown {name}", "value": f"{mdd * 100:.1f}%", "basis": "close-to-close over aligned days"})
    out = t_rd / "tables"
    write_csv(out / f"benchmark_{b_rd.name}.csv", ["metric", "value", "basis"], rows)
    write_atomic(out / f"benchmark_{b_rd.name}.md", f"# {t_rd.name} vs {b_rd.name}\nBuilt by scripts/benchmark_compare.py from cached Finviz daily closes ({len(common)} aligned days to {last}); price returns, split-adjusted as retrieved.\n\n| metric | value | basis |\n|---|---|---|\n" + "\n".join(f"| {r['metric']} | {r['value']} | {r['basis']} |" for r in rows) + "\n")
    print({"aligned_days": len(common), "metrics": len(rows)})


if __name__ == "__main__":
    main()
