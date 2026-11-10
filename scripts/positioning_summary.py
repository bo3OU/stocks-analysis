"""Positioning summary from cached price, short-interest, Reg SHO, earnings-reaction, options and 13D/G files.

Outputs (RESEARCH_DIR/tables/): positioning.csv (metric, value, basis) and positioning.md. Every metric is CALC from cached
rows; the options chain is one retrieval-time snapshot (no IV history, no percentile). Finviz prices are split-adjusted as of
retrieval. Usage: .venv/bin/python -I scripts/positioning_summary.py <TICKER or RESEARCH_DIR> [--history-years 5]
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE if (HERE / "toolkit.py").is_file() else HERE.parents[2] / "scripts"))
from toolkit import fail, fmt, num, parse_date, read_csv, research_dir, write_atomic, write_csv  # noqa: E402


def dedupe(rows, key):
    seen, result = set(), []
    for row in rows:
        identity = key(row)
        if identity not in seen:
            seen.add(identity)
            result.append(row)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--history-years", type=int, default=5)
    a = ap.parse_args()
    if a.history_years < 1 or a.history_years > 100:
        fail("--history-years must be between 1 and 100")
    rd = research_dir(a.folder)
    fin, der = rd / "raw" / "finviz", rd / "derived"
    rows: list[dict] = []

    def local_csv(path):
        if not path.resolve().is_relative_to(rd) or path.is_symlink():
            fail(f"input escapes folder: {path}")
        return read_csv(path)

    def add(metric, value, basis=""):
        rendered = "" if value is None else value if isinstance(value, str) else (fmt(value, 0) if isinstance(value, (int, float)) and abs(value) >= 1000 else fmt(float(value), 4))
        rows.append({"metric": metric, "value": rendered, "basis": basis})

    # One observation per session. A zero/negative close cannot support returns.
    prices = {}
    bad_price_dates = set()
    for r in local_csv(fin / "price_history_daily.csv"):
        d, close = parse_date(r.get("Date")), num(r.get("Close"))
        if d and close is not None and math.isfinite(close) and close > 0:
            volume, high, low = (num(r.get(k)) for k in ("Volume", "High", "Low"))
            if high is not None and (not math.isfinite(high) or high < close):
                print(f"WARN price {d}: invalid high excluded", file=sys.stderr)
                high = None
            if low is not None and (not math.isfinite(low) or low <= 0 or low > close):
                print(f"WARN price {d}: invalid low excluded", file=sys.stderr)
                low = None
            observation = (d, close, volume, high, low)
            if d in prices and prices[d] != observation:
                bad_price_dates.add(d)
            elif d not in bad_price_dates:
                prices[d] = observation
    for d in sorted(bad_price_dates):
        prices.pop(d, None)
        print(f"WARN conflicting daily price rows for {d}: date excluded", file=sys.stderr)
    px = [prices[d] for d in sorted(prices)]
    if px:
        last_d, last_c = px[-1][0], px[-1][1]
        px = [x for x in px if x[0] >= last_d - dt.timedelta(days=366 * a.history_years)]
        add("last_close", last_c, f"Finviz daily close {last_d.isoformat()} (split-adjusted as of retrieval)")
        closes = {x[0]: x[1] for x in px}
        for label, days in (("1m", 30), ("3m", 91), ("6m", 182), ("1y", 365), ("3y", 1095), ("5y", 1826)):
            if days > 366 * a.history_years:
                continue
            ref = max((d for d in closes if d <= last_d - dt.timedelta(days=days)), default=None)
            if ref and px[0][0] <= ref:
                add(f"return_{label}", f"{(last_c / closes[ref] - 1) * 100:.1f}%", f"close {last_c} vs {closes[ref]} on {ref.isoformat()}; price return, no dividends")
        y = [x for x in px if x[0] > last_d - dt.timedelta(days=365)]
        if y:
            hi = max(x[3] if x[3] is not None and x[3] > 0 else x[1] for x in y)
            lo = min(x[4] if x[4] is not None and x[4] > 0 else x[1] for x in y)
            add("52w_high", hi, "max daily high, last 365 days")
            add("52w_low", lo, "min daily low, last 365 days")
            add("pct_below_52w_high", f"{(1 - last_c / hi) * 100:.1f}%", "")
        rets = [math.log(px[i][1] / px[i - 1][1]) for i in range(1, len(px)) if px[i - 1][1] > 0 and px[i][1] > 0]
        for n, lbl in ((30, "30d"), (252, "1y")):
            if len(rets) >= n:
                add(f"realized_vol_{lbl}", f"{statistics.stdev(rets[-n:]) * math.sqrt(252) * 100:.1f}%", f"stdev of last {n} daily log returns x sqrt(252)")
        peak, mdd = 0.0, 0.0
        for x in px:
            peak = max(peak, x[1])
            mdd = min(mdd, x[1] / peak - 1)
        add("max_drawdown_window", f"{mdd * 100:.1f}%", f"close-to-close within the {a.history_years}-year window")
        rec = [x for x in px if x[0] > last_d - dt.timedelta(days=91) and x[2] is not None and math.isfinite(x[2]) and x[2] > 0]
        if rec:
            add("avg_daily_dollar_volume_3m", statistics.mean(x[1] * x[2] for x in rec), "mean of close x volume over ~3 months")
    ev = local_csv(der / "earnings_events.csv")
    ev = sorted(ev, key=lambda r: (parse_date(r.get("filed")) or dt.date.min, r.get("accession") or ""), reverse=True)
    events, bad_events = {}, set()
    for r in ev:
        v = num(r.get("return_pct"))
        if v is None or not math.isfinite(v):
            continue
        key = (r.get("accession") or r.get("filed"), r.get("reaction_date"))
        if key in events and events[key] != v:
            bad_events.add(key)
        elif key not in bad_events:
            events[key] = v
    if bad_events:
        print(f"WARN {len(bad_events)} conflicting earnings-reaction events excluded", file=sys.stderr)
    rets_e = [v for key, v in events.items() if key not in bad_events]
    if rets_e:
        last8 = rets_e[:8]
        add("earnings_reaction_events", len(rets_e), "8-K item 2.02 events in the folder; close-to-close around first session after acceptance; not causal")
        add("earnings_reaction_mean_abs_last8", f"{statistics.mean(abs(x) for x in last8):.1f}%", f"over {len(last8)} events")
        add("earnings_reaction_median_last8", f"{statistics.median(last8):.1f}%", f"positive in {sum(x > 0 for x in last8)} of {len(last8)}")
    si_by_date, bad_si_dates = {}, set()
    for r in local_csv(fin / "short_interest_history.csv"):
        d, v = parse_date(r.get("Settlement Date")), num(r.get("Short Interest"))
        if d is None or v is None or not math.isfinite(v) or v < 0:
            continue
        signature = (v, r.get("Short Float", ""), r.get("Short Ratio", ""))
        if d in si_by_date and si_by_date[d][0] != signature:
            bad_si_dates.add(d)
        elif d not in bad_si_dates:
            si_by_date[d] = (signature, r)
    for d in sorted(bad_si_dates):
        si_by_date.pop(d, None)
        print(f"WARN conflicting short-interest rows for {d}: settlement excluded", file=sys.stderr)
    si = [si_by_date[d][1] for d in sorted(si_by_date, reverse=True)]
    if si:
        s0 = si[0]
        add("short_interest_latest", num(s0["Short Interest"]), f"settlement {s0['Settlement Date']}; FINRA via Finviz; publication lag not verified")
        add("short_float_pct_latest", s0.get("Short Float", ""), "as reported by Finviz")
        add("short_ratio_latest", s0.get("Short Ratio", ""), "days to cover as reported (method of average volume per Finviz)")
        if len(si) > 1 and num(si[1]["Short Interest"]):
            add("short_interest_change_vs_prior", f"{(num(s0['Short Interest']) / num(si[1]['Short Interest']) - 1) * 100:.1f}%", f"vs {si[1]['Settlement Date']}")
        add("short_interest_trend_last6", "; ".join(f"{r['Settlement Date']}={fmt(num(r['Short Interest']), 0)}" for r in si[:6]), "")
    rs = local_csv(der / "finra_regsho_daily.csv")
    regsho_rows: dict[tuple, dict] = {}
    bad_regsho_dates = set()
    for r in rs:
        key = (r.get("Date"), r.get("Symbol"), r.get("Market"))
        if key in regsho_rows and r != regsho_rows[key]:
            bad_regsho_dates.add(key[0])
        elif key[0] not in bad_regsho_dates:
            regsho_rows[key] = r
    for date in sorted(bad_regsho_dates, key=str):
        print(f"WARN conflicting Reg SHO rows for {date}: date excluded", file=sys.stderr)
    rs = list(regsho_rows.values())
    daily: dict[str, tuple[float, float]] = {}
    markets: dict[str, set[str]] = {}
    for r in rs:
        s, t = num(r.get("ShortVolume")), num(r.get("TotalVolume"))
        date = r.get("Date")
        if not date or date in bad_regsho_dates or s is None or t is None or not math.isfinite(s) or not math.isfinite(t) or s < 0 or t <= 0 or s > t:
            continue
        market_set = {m.strip() for m in (r.get("Market") or "").split(",") if m.strip()}
        if not market_set or markets.get(date, set()) & market_set:
            bad_regsho_dates.add(date)
            daily.pop(date, None)
            print(f"WARN overlapping or missing Reg SHO markets for {date}: date excluded", file=sys.stderr)
            continue
        markets.setdefault(date, set()).update(market_set)
        old_s, old_t = daily.get(date, (0.0, 0.0))
        daily[date] = old_s + s, old_t + t
    if daily:
        add("regsho_short_volume_ratio_mean", f"{statistics.mean(s / t for s, t in daily.values()) * 100:.1f}%", f"{len(daily)} trading days; trade-flow measure, NOT short interest")
    chain = local_csv(fin / "options_chain.csv")
    if chain and px:
        by = {}
        for r in chain:
            d = parse_date(r.get("Expiry"))
            if d and d >= last_d:
                by.setdefault(d, []).append(r)
        for d in sorted(by)[:4]:
            unique = {}
            bad_contracts = set()
            for r in by[d]:
                key = r.get("Contract Name") or (r.get("Type"), r.get("Strike"))
                signature = tuple(r.get(k) for k in ("Type", "Strike", "Open Int.", "Volume", "IV"))
                if key in unique and unique[key][0] != signature:
                    bad_contracts.add(key)
                elif key not in bad_contracts:
                    unique[key] = (signature, r)
            if bad_contracts:
                print(f"WARN {len(bad_contracts)} conflicting options contracts for {d}: excluded", file=sys.stderr)
            c = [r for key, (_, r) in unique.items() if key not in bad_contracts]
            if not c:
                continue
            calls = [r for r in c if (r.get("Type") or "").lower() == "call"]
            puts = [r for r in c if (r.get("Type") or "").lower() == "put"]
            oi = lambda items: sum(v for r in items if (v := num(r.get("Open Int."))) is not None and math.isfinite(v) and v >= 0)  # noqa: E731
            vol = lambda items: sum(v for r in items if (v := num(r.get("Volume"))) is not None and math.isfinite(v) and v >= 0)  # noqa: E731
            atm = sorted((r for r in c if (v := num(r.get("Strike"))) is not None and math.isfinite(v) and v > 0), key=lambda r: abs(num(r.get("Strike")) - last_c))[:4]
            ivs = [v for r in atm if (v := num(r.get("IV"))) is not None and math.isfinite(v) and v > 0]
            call_oi, put_oi = oi(calls), oi(puts)
            ratio = f"{put_oi / call_oi:.2f}" if call_oi > 0 else "unknown (zero call OI)"
            add(f"options_{d.isoformat()}", f"call OI {call_oi:.0f}, put OI {put_oi:.0f}, put/call OI {ratio}; volume calls {vol(calls):.0f} puts {vol(puts):.0f}; near-ATM IV {statistics.mean(ivs) * 100:.0f}%" if ivs else f"call OI {call_oi:.0f}, put OI {put_oi:.0f}",
                "snapshot at retrieval; strikes nearest the last close; open interest and volume do not show opening/closing or net exposure")
    own = local_csv(der / "ownership_13dg.csv")
    latest: dict = {}
    for r in sorted(own, key=lambda r: (parse_date(r.get("filed")) or dt.date.min, r.get("accession") or "")):
        person, klass = (r.get("reporting_person") or "").strip(), (r.get("class_title") or "").strip()
        if not person:
            continue
        key = (person, klass)
        filing = (parse_date(r.get("filed")) or dt.date.min, r.get("accession") or "")
        pct = num(r.get("percent_of_class"))
        valid = pct is not None and math.isfinite(pct) and 0 <= pct <= 100
        if key not in latest or filing > latest[key][0]:
            latest[key] = (filing, {pct: r} if valid else {})
        elif filing == latest[key][0] and valid:
            latest[key][1][pct] = r
    known = {key: next(iter(value[1].values())) for key, value in latest.items() if len(value[1]) == 1}
    unknown_count = len(latest) - len(known)
    for key, value in latest.items():
        if len(value[1]) > 1:
            print(f"WARN conflicting 13D/G percentages for {key}: holder excluded", file=sys.stderr)
    if unknown_count:
        add("13dg_latest_pct_unknown_count", unknown_count, "latest filing for these reporting-person/class pairs has no parsed percentage; earlier values are not carried forward")
    for p, r in sorted(known.items(), key=lambda kv: (-(num(kv[1].get("percent_of_class")) or 0), kv[0]))[:8]:
        add(f"13dg_{p[0][:40]}" + (f"_{p[1][:24]}" if p[1] else ""), f"{r.get('percent_of_class', '')}% ({r.get('form', '')} filed {r.get('filed', '')}, event {r.get('event_date', '')})", "latest parsed percentage per reporting person and class in this folder; a missing holder is not a sale")
    if not rows:
        fail("no positioning inputs found")
    out = rd / "tables"
    if out.is_symlink() or not out.resolve().is_relative_to(rd):
        fail("tables directory escapes folder")
    write_csv(out / "positioning.csv", ["metric", "value", "basis"], rows)
    md = [f"# Positioning summary: {rd.name}", "Built by scripts/positioning_summary.py (CALC from cached files; Finviz prices split-adjusted as of retrieval).", "", "| metric | value | basis |", "|---|---|---|"]
    md += ["| " + " | ".join(str(r[k]).replace("|", "\\|").replace("\n", " ").replace("\r", " ") for k in ("metric", "value", "basis")) + " |" for r in rows]
    write_atomic(out / "positioning.md", "\n".join(md) + "\n")
    print({"metrics": len(rows)})


if __name__ == "__main__":
    main()
