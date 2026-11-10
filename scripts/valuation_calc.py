"""Deterministic valuation arithmetic from explicit agent assumptions.

Subcommands: bridge, dcf, reverse, grid, rnpv. JSON inputs and output columns follow
scripts/valuation_calc.py. Units are those of the supplied cash flows. Use
--out PATH inside a research folder's tables/ directory to save a calculation.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if not (HERE / "toolkit.py").is_file():
    sys.path.insert(1, str(HERE.parents[2] / "scripts"))
from toolkit import RESEARCH, fail, write_atomic  # noqa: E402


def finite(value, name: str) -> float:
    if isinstance(value, bool):
        fail(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        fail(f"{name} must be a finite number")
    if not math.isfinite(result):
        fail(f"{name} must be a finite number")
    return result


def checked(value: float, name: str) -> float:
    if not math.isfinite(value):
        fail(f"{name} overflowed or is not finite")
    return value


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject ambiguous JSON assumptions instead of silently taking the last key."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def discount_factor(rate: float, years: float) -> float:
    try:
        denominator = (1 + rate) ** years
    except OverflowError:
        return 0.0
    if denominator == 0:
        fail("discount factor underflowed; revise discount_rate or years")
    return checked(1 / denominator, "discount factor")


def terminal_value(term: dict, last: float, rate: float) -> float:
    if not isinstance(term, dict) or len(set(term) & {"growth", "multiple"}) != 1:
        fail("terminal needs exactly one of growth or multiple")
    if "growth" in term:
        g = finite(term["growth"], "terminal.growth")
        if g <= -1 or g >= rate:
            fail("terminal growth must be greater than -1 and below the discount rate")
        return checked(last * (1 + g) / (rate - g), "terminal value")
    multiple = finite(term["multiple"], "terminal.multiple")
    if multiple < 0:
        fail("terminal multiple must be nonnegative")
    return checked(last * multiple, "terminal value")


def dcf(inp: dict) -> dict:
    if not isinstance(inp, dict):
        fail("inputs must be a JSON object")
    r = finite(inp.get("discount_rate"), "discount_rate")
    if r <= -1:
        fail("discount_rate must be greater than -1")
    cfs = inp.get("cash_flows")
    if not isinstance(cfs, list) or not cfs:
        fail("cash_flows must be a nonempty array")
    if inp.get("terminal_base", "last_cash_flow") != "last_cash_flow":
        fail("terminal_base must be last_cash_flow")
    scale = finite(inp.get("scale", 1.0), "scale")
    if scale < 0:
        fail("scale must be nonnegative")
    if not isinstance(inp.get("mid_year", False), bool):
        fail("mid_year must be boolean")
    mid = 0.5 if inp.get("mid_year") else 0.0
    pv_rows, pv_sum, last_t = [], 0.0, 0.0
    for i, cf in enumerate(cfs):
        if not isinstance(cf, dict):
            fail(f"cash_flows[{i}] must be an object")
        t = finite(cf.get("year"), f"cash_flows[{i}].year")
        if t > 100:
            fail(f"cash_flows[{i}].year={t:g} looks like a calendar year; year means periods from the valuation date (use rnpv with base_year, or subtract it)")
        if t <= 0 or t <= last_t or t <= mid:
            fail("cash flow years must be positive, strictly increasing, and after the valuation date")
        probability = finite(cf.get("probability", 1.0), f"cash_flows[{i}].probability")
        if not 0 <= probability <= 1:
            fail("cash flow probability must be between 0 and 1")
        v = checked(finite(cf.get("value"), f"cash_flows[{i}].value") * probability * scale, "cash flow")
        factor = discount_factor(r, t - mid)
        pv = checked(v * factor, "present value")
        pv_rows.append({"year": t, "value_prob_weighted_scaled": v, "discount_factor": factor, "pv": pv})
        pv_sum = checked(pv_sum + pv, "explicit present value")
        last_t = t
    tv = pv_tv = None
    term = inp.get("terminal")
    if term is not None:
        last = pv_rows[-1]["value_prob_weighted_scaled"]
        tv = terminal_value(term, last, r)
        pv_tv = checked(tv * discount_factor(r, last_t), "terminal present value")
    ev = checked(pv_sum + (pv_tv if pv_tv is not None else 0), "enterprise value")
    out = {"inputs": inp, "pv_explicit": pv_sum, "terminal_value": tv, "pv_terminal": pv_tv, "enterprise_value": ev, "rows": pv_rows,
           "formula": "EV = sum(value*probability*scale/(1+r)^(t-mid)) + terminal/(1+r)^T; terminal = last*(1+g)/(r-g) or last*multiple"}
    if "shares" in inp and "net_cash" not in inp:
        fail("shares requires net_cash for an equity value per share")
    if "net_cash" in inp:
        out["equity_value"] = checked(ev + finite(inp["net_cash"], "net_cash"), "equity value")
        if "shares" in inp:
            shares = finite(inp["shares"], "shares")
            if shares <= 0:
                fail("shares must be positive")
            out["equity_value_per_share"] = checked(out["equity_value"] / shares, "equity value per share")
    return out


def rnpv(inp: dict) -> dict:
    """Risk-adjusted NPV for a development-stage asset: revenue cash flows are weighted by the probability of success, development costs are not.
    Inputs: base_year, revenue [{year,value}], development_costs [{year,value}] (calendar years after base_year; positive cost numbers), operating_margin, tax_rate, probability_of_success,
    discount_rate, optional terminal/net_cash/shares/mid_year. Terminal value uses risk-adjusted after-tax profit in the last revenue year,
    excluding development costs; the caller chooses and labels every assumption."""
    pos = finite(inp.get("probability_of_success"), "probability_of_success")
    margin = finite(inp.get("operating_margin"), "operating_margin")
    tax = finite(inp.get("tax_rate", 0.0), "tax_rate")
    if not 0 <= pos <= 1 or not 0 <= tax < 1 or margin > 1:
        fail("probability_of_success must be 0..1, tax_rate 0..<1, operating_margin <= 1")
    base_year = finite(inp.get("base_year"), "base_year (the valuation year; cash flows are at the end of each later calendar year)")
    if not base_year.is_integer() or not 1900 <= base_year <= 2200:
        fail("base_year must be a calendar year between 1900 and 2200")
    rev, cost = {}, {}
    for key, store in (("revenue", rev), ("development_costs", cost)):
        entries = inp.get(key, [])
        if entries is None:
            entries = []
        if not isinstance(entries, list):
            fail(f"{key} must be an array")
        for i, row in enumerate(entries):
            if not isinstance(row, dict):
                fail(f"{key}[{i}] must be an object")
            calendar_year = finite(row.get("year"), f"{key}[{i}].year")
            if not calendar_year.is_integer():
                fail(f"{key}[{i}].year must be a calendar year")
            y = calendar_year - base_year
            if y < 1:
                fail(f"{key} year must be after base_year {base_year:g}")
            value = finite(row.get("value"), f"{key}[{i}].value")
            if value < 0:
                fail(f"{key}[{i}].value must be nonnegative")
            store[y] = checked(store.get(y, 0.0) + value, f"{key} total")
    if not rev and not cost:
        fail("revenue and development_costs are both empty")
    def after_tax_profit(revenue: float) -> float:
        profit = checked(revenue * margin, "operating profit")
        # A loss does not create an immediate tax refund in this standalone asset model.
        return checked(profit - max(profit, 0.0) * tax, "after-tax operating profit")

    cfs = [{"year": y, "value": checked(after_tax_profit(rev.get(y, 0.0)) * pos - cost.get(y, 0.0), "risk-adjusted cash flow"), "probability": 1.0} for y in sorted(set(rev) | set(cost))]
    base = {k: v for k, v in inp.items() if k in ("discount_rate", "terminal", "terminal_base", "mid_year", "shares", "net_cash", "scale")}
    term = base.pop("terminal", None)
    out = dcf({**base, "cash_flows": cfs})
    if term is not None:
        if not rev:
            fail("rnpv terminal requires at least one revenue year")
        terminal_year = max(rev)
        last_profit = checked(after_tax_profit(rev[terminal_year]) * pos * finite(base.get("scale", 1.0), "scale"), "terminal profit")
        tv = terminal_value(term, last_profit, finite(base.get("discount_rate"), "discount_rate"))
        pv_tv = checked(tv * discount_factor(finite(base["discount_rate"], "discount_rate"), terminal_year), "terminal present value")
        out["inputs"]["terminal"] = term
        out["terminal_value"] = tv
        out["pv_terminal"] = pv_tv
        out["enterprise_value"] = checked(out["pv_explicit"] + pv_tv, "enterprise value")
        if "equity_value" in out:
            out["equity_value"] = checked(out["enterprise_value"] + finite(base["net_cash"], "net_cash"), "equity value")
            if "equity_value_per_share" in out:
                out["equity_value_per_share"] = checked(out["equity_value"] / finite(base["shares"], "shares"), "equity value per share")
        out["formula"] = "EV = sum(risk-adjusted cash flows/(1+r)^(t-mid)) + terminal/(1+r)^T; terminal is based on after-tax profit in the last revenue year T, excluding development costs"
    out["rnpv_inputs"] = inp
    out["formula_rnpv"] = "profit_y = revenue_y*operating_margin; cash_flow_y = (profit_y - max(profit_y,0)*tax_rate)*probability_of_success - development_costs_y; terminal, if supplied, uses last revenue-year after-tax profit before development costs"
    return out


def reverse(inp: dict, target: float) -> dict:
    target = finite(target, "target_ev")
    dcf(inp)
    base = dcf({**inp, "scale": 1.0})["enterprise_value"]
    if base == 0:
        fail("base EV is zero; cannot scale")
    scale = checked(target / base, "reverse scale")
    if scale < 0:
        fail("target EV cannot be reached with a nonnegative scale")
    ev = dcf({**inp, "scale": scale})["enterprise_value"]
    return {"inputs": inp, "target_ev": target, "scale_factor": scale, "ev_at_scale": ev,
            "meaning": "set the scale input to scale_factor (probabilities and terminal base unchanged) to reach the target EV; the scale is not a forecast"}


def setpath(d: dict, key: str, value: float):
    if key in ("discount_rate", "scale"):
        d[key] = value
    elif key in ("terminal.growth", "terminal.multiple"):
        if not isinstance(d.get("terminal"), dict) or key.split(".")[1] not in d["terminal"]:
            fail(f"grid axis {key} is absent from terminal inputs")
        d["terminal"][key.split(".")[1]] = value
    else:
        fail(f"unsupported grid axis: {key}")


def grid_calc(inp: dict, vary: list[str]) -> dict:
    axes = []
    for spec in vary:
        key, sep, values = spec.partition("=")
        if not sep or key not in ("discount_rate", "terminal.growth", "terminal.multiple", "scale") or any(key == old for old, _ in axes):
            fail(f"invalid or duplicate grid axis: {key}")
        parts = values.split(",")
        if any(not v.strip() for v in parts):
            fail(f"grid axis {key} contains an empty value")
        vals = [finite(v, f"grid axis {key}") for v in parts]
        if not vals:
            fail(f"grid axis {key} has no values")
        axes.append((key, vals))
    size = math.prod(len(vals) for _, vals in axes)
    if size > 1000:
        fail("grid exceeds 1000 cells")
    rows = []
    for combo in itertools.product(*(vals for _, vals in axes)):
        cur = json.loads(json.dumps(inp, allow_nan=False))
        for (key, _), value in zip(axes, combo):
            setpath(cur, key, value)
        rows.append({**{key: value for (key, _), value in zip(axes, combo)}, "enterprise_value": dcf(cur)["enterprise_value"]})
    return {"inputs": inp, "grid": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    sub = ap.add_subparsers(dest="cmd", required=True)
    bridge = sub.add_parser("bridge")
    bridge.add_argument("--price", type=float, required=True)
    bridge.add_argument("--shares", type=float, required=True)
    bridge.add_argument("--cash", type=float, default=0.0)
    bridge.add_argument("--debt", type=float, default=0.0)
    bridge.add_argument("--other-claims", type=float, default=0.0)
    for name in ("dcf", "reverse", "grid", "rnpv"):
        parser = sub.add_parser(name)
        parser.add_argument("--inputs", required=True)
        if name == "reverse":
            parser.add_argument("--target-ev", type=float, required=True)
        if name == "grid":
            parser.add_argument("--vary", action="append", required=True)
    for parser in (bridge, *[sub.choices[name] for name in ("dcf", "reverse", "grid", "rnpv")]):
        parser.add_argument("--out", default=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.cmd == "bridge":
        price, shares = finite(a.price, "price"), finite(a.shares, "shares")
        cash, debt, claims = (finite(getattr(a, name), name) for name in ("cash", "debt", "other_claims"))
        if price < 0 or shares <= 0 or cash < 0 or debt < 0 or claims < 0:
            fail("price, cash, debt and claims must be nonnegative; shares must be positive")
        mc = checked(price * shares, "market cap")
        res = {"inputs": vars(a) | {"cmd": "bridge"}, "market_cap": mc,
               "enterprise_value": checked(mc + debt + claims - cash, "enterprise value"),
               "formula": "EV = price*shares + debt + other_claims - cash"}
    else:
        try:
            inp = json.loads(Path(a.inputs).read_text(encoding="utf-8"),
                             parse_constant=lambda x: fail(f"nonfinite JSON number: {x}"),
                             parse_float=lambda x: finite(x, "JSON number"),
                             object_pairs_hook=unique_object)
        except (OSError, ValueError) as e:
            fail(f"cannot read inputs: {e}")
        if not isinstance(inp, dict):
            fail("inputs must be a JSON object")
        res = dcf(inp) if a.cmd == "dcf" else rnpv(inp) if a.cmd == "rnpv" else reverse(inp, a.target_ev) if a.cmd == "reverse" else grid_calc(inp, a.vary)
    output = json.dumps(res, indent=1, allow_nan=False) + "\n"
    if a.out:
        raw = Path(a.out).absolute()
        if ".." in raw.parts:
            fail("--out must not contain parent traversal")
        research_root = RESEARCH.resolve()
        for component in (raw, *raw.parents):
            if component == RESEARCH:
                break
            if component.is_symlink():
                fail(f"refusing to write through a symlink: {component}")
        p = raw.resolve()
        try:
            relative = p.relative_to(research_root)
        except ValueError:
            fail("--out must be inside research/")
        if len(relative.parts) != 3 or relative.parts[1] != "tables" or p.suffix.lower() != ".json" or relative.parts[2] == "PREPARED.json":
            fail("--out must be a JSON calculation in research/<folder>/tables/ (not PREPARED.json)")
        if not (research_root / relative.parts[0] / "identity.json").is_file():
            fail("--out needs an existing research folder with identity.json")
        write_atomic(p, output)
    print(output, end="")


if __name__ == "__main__":
    main()
