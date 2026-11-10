"""Cash runway and dilution scenarios from the cached quarterly statements. Arithmetic only: assumptions are command-line values
the agent chooses and labels as its own.

Model per scenario g (burn growth per quarter): burn_t = base_burn * (1+g)^t for t = 1..N; cash_t = cash_{t-1} - burn_t + raises_t;
shares_t = shares_{t-1} + raise_amount / raise_price. base_burn = latest quarter operating cash use (default) or the TTM average.
Operating cash use is used as burn; investing and financing flows other than listed raises are ignored.
Outputs (RESEARCH_DIR/tables/): runway_scenarios.csv and runway_scenarios.md.
Usage: .venv/bin/python -I scripts/runway_scenarios.py <TICKER or RESEARCH_DIR> [--burn-growth 0,0.05,0.10] [--horizon-quarters 12]
         [--base latest|ttm] [--raise QUARTER:AMOUNT:PRICE ...]   (QUARTER 1 = first quarter after the latest reported one; AMOUNT in statement units)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if not (HERE / "build_tables.py").is_file():
    sys.path.insert(1, str(HERE.parents[2] / "scripts"))
from build_tables import load_statement, val  # noqa: E402
from toolkit import fail, fmt, research_dir, safe_child, write_atomic, write_csv  # noqa: E402


def add_quarters(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + 3 * n, 12)
    y, m = d.year + y, m + 1
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    source_next = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    source_month_end = source_next - dt.timedelta(days=1)
    return last if d == source_month_end else dt.date(y, m, min(d.day, last.day))


def finite_number(raw: str, name: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        fail(f"{name} must be a finite number")
    if not math.isfinite(value):
        fail(f"{name} must be a finite number")
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--burn-growth", default="0,0.05,0.10")
    ap.add_argument("--horizon-quarters", type=int, default=12)
    ap.add_argument("--base", choices=("latest", "ttm"), default="latest")
    ap.add_argument("--raise", dest="raises", action="append", default=[])
    a = ap.parse_args()
    if not 1 <= a.horizon_quarters <= 40:
        fail("--horizon-quarters must be 1..40")
    growths = [finite_number(x, "--burn-growth") for x in a.burn_growth.split(",") if x.strip() != ""]
    if not growths or any(g <= -1 or g > 5 for g in growths):
        fail("--burn-growth values must be > -1 and <= 5")
    raises = []
    for r in a.raises:
        try:
            q, amt, px = r.split(":")
            q, amt, px = int(q), finite_number(amt, "--raise amount"), finite_number(px, "--raise price")
        except ValueError:
            fail(f"--raise needs QUARTER:AMOUNT:PRICE, got {r!r}")
        if not 1 <= q <= a.horizon_quarters or amt <= 0 or px <= 0:
            fail(f"--raise out of range: {r}")
        raises.append((q, amt, px))
    rd = research_dir(a.folder)
    for rel in ("identity.json", "raw/finviz/statements_BQ.csv", "raw/finviz/statements_CQ.csv", "raw/finviz/statements_IQ.csv", "tables"):
        if safe_child(rd, rel) is None:
            fail(f"path escapes research folder: {rel}")
    try:
        ident = json.loads((rd / "identity.json").read_text(encoding="utf-8"))
        if not isinstance(ident, dict):
            fail("identity.json must be an object")
    except (OSError, ValueError) as e:
        fail(f"cannot read identity.json: {e}")
    fin = rd / "raw" / "finviz"
    qb, qc, qi = (load_statement(fin / f"statements_{s}Q.csv") for s in "BCI")
    if not (qb and qc and qi):
        fail("needs raw/finviz quarterly statements (not available in as-of folders); use tables/xbrl_quarterly.csv by hand there")
    cash = val(qb[1], "Cash & Short Term Investments", 0)
    shares = val(qi[1], "Shares Outstanding", 0)
    ends = [p["end"] for p in qc[0][:4]]
    cfo = [val(qc[1], "Cash from Operating Activities", i) for i in range(4)]
    if cash is None or cfo[0] is None or not ends[0]:
        fail("latest cash or operating cash flow missing")
    periods_needed = 4 if a.base == "ttm" else 1
    if any(p["length"].strip().lower() not in ("3 months", "3 month") for p in qc[0][:periods_needed]) or len(qc[0]) < periods_needed:
        fail("runway needs discrete 3-month cash-flow columns; cumulative or unknown period lengths cannot be used as quarterly burn")
    if cash < 0 or (shares is not None and shares <= 0):
        fail("latest cash must be nonnegative and shares, if present, must be positive")
    if raises and shares is None:
        fail("share count is missing; cannot calculate dilution from --raise")
    if qb[0][0]["end"] != qc[0][0]["end"]:
        fail("balance sheet and cash-flow latest dates differ")
    if shares is not None and qi[0][0]["end"] != qc[0][0]["end"]:
        fail("income statement shares and cash-flow latest dates differ")
    if a.base == "ttm":
        if len(ends) < 4 or any(x is None for x in cfo) or not all(ends[i] and ends[i + 1] and 70 <= (ends[i] - ends[i + 1]).days <= 110 for i in range(3)):
            fail("TTM base needs four consecutive discrete quarters")
        base = -sum(cfo) / 4
    else:
        base = -cfo[0]
    if base <= 0:
        fail("operating cash flow is not negative in the base period: no burn runway to model")
    cur = ident.get("finviz_statement_currency") or "unknown"
    rows = []
    for g in growths:
        c, s, ended = cash, shares, None
        for t in range(1, a.horizon_quarters + 1):
            burn = base * (1 + g) ** t
            if not math.isfinite(burn):
                fail("scenario burn overflowed")
            for q, amt, px in raises:
                if q == t:
                    c += amt
                    s = (s + amt / px) if s is not None else None
            c -= burn
            if not math.isfinite(c) or (s is not None and not math.isfinite(s)):
                fail("scenario cash or shares overflowed")
            if c < 0 and ended is None:
                ended = t
            rows.append({"burn_growth_per_quarter": g, "quarter": t, "quarter_end": add_quarters(ends[0], t).isoformat(), "burn": fmt(burn, 0), "cash_end": fmt(c, 0),
                         "shares_end": fmt(s, 0) if s is not None else "", "cash_negative": "yes" if c < 0 else ""})
    out = rd / "tables"
    write_csv(out / "runway_scenarios.csv", ["burn_growth_per_quarter", "quarter", "quarter_end", "burn", "cash_end", "shares_end", "cash_negative"], rows)
    md = [f"# Runway scenarios: {rd.name}", f"Built by scripts/runway_scenarios.py. Currency/units as stored in the statements ({cur}). Start: cash and short-term investments {fmt(cash, 0)} at {ends[0]}; base quarterly operating cash use ({a.base}) {fmt(base, 0)}; shares {fmt(shares, 0)}.",
          "Formula: burn_t = base*(1+g)^t; cash_t = cash_(t-1) - burn_t + raises_t; shares += amount/price. Operating cash flow only; no interest, capex, investing or financing flows other than the listed raises. Assumptions are the caller's, not forecasts.",
          f"Raises: {', '.join(f'q{q}: {fmt(amt, 0)} at {px}' for q, amt, px in raises) or 'none'}", "", "| growth | first quarter cash < 0 | cash at end of horizon | shares at end |", "|---|---|---|---|"]
    for g in growths:
        rs = [r for r in rows if r["burn_growth_per_quarter"] == g]
        neg = next((r for r in rs if r["cash_negative"]), None)
        md.append(f"| {g * 100:+.6g}% per quarter | {('q' + str(neg['quarter']) + ' (' + neg['quarter_end'] + ')') if neg else 'not within horizon'} | {rs[-1]['cash_end']} | {rs[-1]['shares_end']} |")
    write_atomic(out / "runway_scenarios.md", "\n".join(md) + "\n")
    print("\n".join(md[-(len(growths) + 2):]))


if __name__ == "__main__":
    main()
