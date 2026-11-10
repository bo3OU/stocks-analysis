"""Insider ledger and rule-screen flags from derived/insider_filings.csv, form144_notices.csv and filings_index.csv.

Outputs (RESEARCH_DIR/digest/): insider_ledger.csv, insider_flags.csv, form144_match.csv, insider_summary.md.
Flags are REVIEW CANDIDATES per agents/RULEBOOK_FILINGS.md (S16-A, S16-B, R10B5-A, F144-A), never findings of violations:
exemptions, filer status and exact timing facts are not in the data. Unknown inputs yield UNKNOWN rows, not guesses.
Usage: .venv/bin/python -I scripts/build_insider_ledger.py <TICKER or RESEARCH_DIR>
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if not (SCRIPT_DIR / "toolkit.py").is_file():
    SCRIPT_DIR = SCRIPT_DIR.parents[2] / "scripts"  # review copy under revised/round<N>/scripts
sys.path.insert(0, str(SCRIPT_DIR))
from toolkit import add_business_days, clean_cell, fail, fmt, num, parse_date, read_csv, research_dir, safe_child, write_atomic, write_csv  # noqa: E402

CATEGORY = {"P": "open_market_purchase", "S": "open_market_sale", "A": "award_grant", "M": "derivative_exercise_conversion",
            "X": "derivative_exercise_conversion", "C": "derivative_conversion", "F": "tax_withholding", "G": "gift",
            "D": "disposition_to_issuer", "J": "other", "I": "discretionary_transaction", "W": "will_inheritance",
            "L": "small_acquisition", "U": "tender_offer", "Z": "voting_trust", "V": "voluntarily_reported", "K": "equity_swap", "H": "expiration", "E": "short_expiration", "O": "out_of_money_exercise"}
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
ADOPT_RE = re.compile(r"(?:adopt(?:ed|ion)|entered into|established)[^.;]{0,160}?\b(?:on|as of|dated)\s+((?:%s)\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})" % MONTHS, re.I)
SUFFIX = {"JR", "SR", "II", "III", "IV", "MD", "PHD"}
LEDGER_FIELDS = ["accession", "form", "owner", "owner_key", "relationship", "officer_title", "table", "security",
                 "date", "filed", "code", "category", "acq_disp", "shares", "price", "value_usd", "shares_after",
                 "rule_10b5_1", "plan_adoption_date", "source_url", "footnotes"]


def person_tokens(name: str) -> frozenset:
    toks = [t for t in re.sub(r"[^A-Za-z ]", " ", name or "").upper().split() if t not in SUFFIX]
    return frozenset(toks)


def same_person(a: frozenset, b: frozenset) -> bool:
    # Subset matching makes JOHN SMITH and JOHN A SMITH (or two relatives) identical.
    return bool(a) and a == b


def possibly_same_class(notice: str, sale: str) -> bool:
    """Reject only explicit class conflicts; vague titles remain possible matches."""
    a, b = (notice or "").casefold(), (sale or "").casefold()
    if ("preferred" in a and ("common" in b or "ordinary" in b) or
            "preferred" in b and ("common" in a or "ordinary" in a)):
        return False
    labels = [re.search(r"\b(class|series)\s+([a-z0-9]+)\b", title) for title in (a, b)]
    return not (labels[0] and labels[1] and labels[0].group(1) == labels[1].group(1)
                and labels[0].group(2) != labels[1].group(2))


def adoption_date(footnotes: str) -> dt.date | None:
    # A modification can restart the cooling-off clock. Without a verified effective
    # modification date, an earlier adoption date cannot support a timing flag.
    if re.search(r"\b(?:modified|modification|amended|amendment)\b", footnotes or "", re.I):
        return None
    dates = set()
    for sent in re.split(r"(?<=[.;])\s+(?=[A-Z(])", footnotes or ""):
        if "10b5-1" in sent or "trading plan" in sent.lower() or "trading arrangement" in sent.lower():
            for m in ADOPT_RE.finditer(sent):
                s = m.group(1)
                for fmt_ in ("%B %d, %Y", "%B %d %Y", "%m/%d/%Y", "%Y-%m-%d"):
                    try:
                        dates.add(dt.datetime.strptime(re.sub(r"\s+", " ", s), fmt_).date())
                        break
                    except ValueError:
                        pass
    return next(iter(dates)) if len(dates) == 1 else None


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return dt.date(y, m, day)


def truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("true", "1", "yes", "y")


def plan_checkbox(v: str) -> str:
    s = (v or "").strip().lower()
    if truthy(s):
        return "yes"
    return "no" if s in ("false", "0", "no", "n") else "UNKNOWN"


def finite_num(v) -> float | None:
    n = num(v)
    return n if n is not None and math.isfinite(n) else None


def input_csv(rd: Path, rel: str) -> list[dict]:
    p = safe_child(rd, rel)
    if p is None:
        fail(f"input escapes research folder: {rel}")
    return read_csv(p)


def owner_identity(r: dict) -> str:
    ciks = [x.strip() for x in (r.get("owner_ciks") or r.get("owner_cik") or "").split(";") if x.strip()]
    names = [x.strip() for x in (r.get("owner") or "").split(";") if x.strip()]
    if len(ciks) == 1 and len(names) <= 1:
        return ciks[0]
    if not ciks and len(names) == 1:
        return "name:" + names[0].casefold()
    return ""  # Several reporting owners cannot be assigned to one transaction line.


def flag(rule: str, x: dict, detail: str, status: str, risks: str = "") -> dict:
    return {"rule_id": rule, "owner": x.get("owner", ""), "accession": x.get("accession", ""),
            "event_date": x.get("date", ""), "filed": x.get("filed", ""), "detail": detail,
            "status": status, "false_positive_risks": risks}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_insider_ledger.py <TICKER or RESEARCH_DIR>")
    rd = research_dir(sys.argv[1])
    identity_path = safe_child(rd, "identity.json")
    if identity_path is None:
        fail("identity.json escapes research folder")
    try:
        ident = json.loads(identity_path.read_text())
    except (OSError, ValueError, UnicodeError) as exc:
        fail(f"cannot read identity.json: {exc}")
    if not isinstance(ident, dict):
        fail("identity.json must contain an object")
    filer_type = str(ident.get("filer_type") or "")
    fpi = filer_type.lower().startswith("foreign") or filer_type.upper() in ("FPI", "FOREIGN")
    issuer_type_known = fpi or "domestic" in filer_type.lower()
    rows = input_csv(rd, "derived/insider_filings.csv")
    n144 = input_csv(rd, "derived/form144_notices.csv")
    index = input_csv(rd, "filings_index.csv")
    missing_inputs = [rel for rel in ("derived/insider_filings.csv", "derived/form144_notices.csv", "filings_index.csv") if not (rd / rel).is_file()]
    periodic = sorted(((parse_date(r.get("reportDate")), parse_date(r.get("filingDate")), r.get("form", ""), r.get("accessionNumber", "")) for r in index
                       if r.get("form") in (("20-F",) if fpi else ("10-Q", "10-K")) and parse_date(r.get("reportDate")) and parse_date(r.get("filingDate"))), key=lambda x: (x[0], x[1], x[3]))
    ledger, flags = [], []
    late_seen = set()
    for r in rows:
        if r.get("table") not in ("non_derivative_transaction", "derivative_transaction"):
            continue
        d, f = parse_date(r.get("date")), parse_date(r.get("filed"))
        shares, price = finite_num(r.get("shares")), finite_num(r.get("price"))
        code = (r.get("code") or "").strip().upper()[:1]
        owner_key = owner_identity(r)
        ad = adoption_date(r.get("footnotes", ""))
        value = shares * price if shares is not None and price is not None else None
        if value is not None and not math.isfinite(value):
            value = None
        category = ("derivative_purchase" if code == "P" else "derivative_sale") if r.get("table") == "derivative_transaction" and code in ("P", "S") else CATEGORY.get(code, "unclassified" if code else "no_code")
        row = {"accession": r.get("accession", ""), "form": r.get("form", ""), "owner": r.get("owner", ""), "owner_key": owner_key, "relationship": r.get("relationship", ""),
               "officer_title": r.get("officer_title", ""), "table": r.get("table", ""), "security": r.get("security", ""), "date": r.get("date", ""),
               "filed": r.get("filed", ""), "code": code, "category": category,
               "acq_disp": r.get("acq_disp", ""), "shares": r.get("shares", "") if shares is not None else "", "price": r.get("price", ""),
               "value_usd": fmt(value, 2) if value is not None and ident.get("xbrl_reporting_currency") == "USD" else "", "shares_after": r.get("shares_after", ""),
               "rule_10b5_1": plan_checkbox(r.get("rule_10b5_1", "")), "plan_adoption_date": ad.isoformat() if ad else "",
               "source_url": r.get("source_url", ""), "footnotes": clean_cell(r.get("footnotes", ""), 400)}
        ledger.append(row)
        # S16-A: original Form 4 later than two business days after the transaction (candidate only)
        if row["form"] == "4" and (not d or not f):
            key = (row["accession"], row["owner"], row["date"])
            if key not in late_seen:
                late_seen.add(key)
                flags.append(flag("S16-A", row, "UNKNOWN: transaction date or filing date unavailable", "UNKNOWN"))
        if row["form"] == "4" and d and f:
            due = add_business_days(d, 2)
            key = (row["accession"], row["owner"], row["date"])
            if f > due and key not in late_seen:
                late_seen.add(key)
                if fpi or not issuer_type_known:
                    flags.append(flag("S16-A", row, f"UNKNOWN: filed after {due.isoformat()}, but issuer type or FPI Section 12 registration and exemption are unverified", "UNKNOWN"))
                else:
                    flags.append(flag("S16-A", row, f"filed {(f - d).days} calendar days after transaction; due {due.isoformat()} (two US business days)", "review candidate", "late-filing exceptions, after-hours acceptance rules, aggregated or deferred reporting, amended facts"))
    # S16-B: same-owner non-derivative open-market P then S (or S then P) less than six months apart; domestic issuers only
    if fpi:
        flags.append({"rule_id": "S16-B", "owner": "", "accession": "", "event_date": "", "filed": "", "detail": "skipped: foreign private issuer (Section 16(b) inapplicable; see S16-C)", "status": "not applicable", "false_positive_risks": ""})
    elif not issuer_type_known:
        flags.append({"rule_id": "S16-B", "owner": "", "accession": "", "event_date": "", "filed": "", "detail": "UNKNOWN: issuer type unavailable", "status": "UNKNOWN", "false_positive_risks": ""})
    else:
        by_owner = collections.defaultdict(list)
        amended_classes = {(x["owner_key"], x["security"]) for x in ledger
                           if x["form"].endswith("/A") and x["owner_key"] and x["security"]}
        for x in ledger:
            if x["table"] == "non_derivative_transaction" and x["code"] in ("P", "S"):
                if not parse_date(x["date"]):
                    flags.append(flag("S16-B", x, "UNKNOWN: transaction date unavailable for six-month pairing", "UNKNOWN"))
                    continue
                if not x["owner_key"] or not x["security"]:
                    flags.append(flag("S16-B", x, "UNKNOWN: reporting owner or security class cannot be assigned to this transaction", "UNKNOWN"))
                    continue
                by_owner[(x["owner_key"], x["security"])].append(x)
        for (ok, sec), xs in sorted(by_owner.items()):
            buys = [x for x in xs if x["code"] == "P"]
            sells = [x for x in xs if x["code"] == "S"]
            if (ok, sec) in amended_classes:
                if buys and sells:
                    flags.append(flag("S16-B", xs[0],
                                      f"UNKNOWN: amended filing for {sec}; original and corrected transaction lines cannot be reconciled from the cache",
                                      "UNKNOWN", "review the original and amended Forms 4/5"))
                continue
            seen_pairs = set()
            for b in buys:
                for s in sells:
                    db, ds = parse_date(b["date"]), parse_date(s["date"])
                    lo, hi = (db, ds) if db <= ds else (ds, db)
                    if hi < add_months(lo, 6):
                        pair_key = (b["accession"], b["date"], b["shares"], b["price"],
                                    s["accession"], s["date"], s["shares"], s["price"])
                        if pair_key in seen_pairs:
                            continue
                        seen_pairs.add(pair_key)
                        pair = {"owner": b["owner"], "accession": f"{b['accession']}+{s['accession']}", "date": f"{b['date']}/{s['date']}", "filed": ""}
                        missing = any(finite_num(x[k]) is None for x in (b, s) for k in ("shares", "price")) or not b["relationship"] or not s["relationship"]
                        flags.append(flag("S16-B", pair, f"P {b['shares']} @ {b['price']} on {b['date']} and S {s['shares']} @ {s['price']} on {s['date']} ({sec}); profit not computed",
                                          "UNKNOWN" if missing else "review candidate", "exemptions, non-insider status at one leg, matching rules, units differing by class"))
    amended_owners = {x["owner_key"] for x in ledger if x["form"].endswith("/A") and x["owner_key"]}
    # R10B5-A: sales under a 10b5-1 plan with a documented adoption date inside the cooling-off window
    f144 = []
    for n in n144:
        f144.append({**n, "_tok": person_tokens(n.get("person", "")), "_sale": parse_date(n.get("approx_sale_date")), "_filed": parse_date(n.get("filed"))})
    for x in ledger:
        if x["code"] == "S" and x["rule_10b5_1"] == "yes":
            if x["form"].endswith("/A") or (x["owner_key"] and x["owner_key"] in amended_owners):
                flags.append(flag("R10B5-A", x, "UNKNOWN: amended ownership filing; plan and sale details need reconciliation", "UNKNOWN"))
                continue
            d = parse_date(x["date"])
            ad = parse_date(x["plan_adoption_date"])
            src = "Form 4 footnote"
            if not ad and d:
                tok = person_tokens(x["owner"])
                candidates = {pa for n in f144 if (pa := parse_date(n.get("plan_adoption_date")))
                              and same_person(tok, n["_tok"]) and n["_filed"] and abs((n["_filed"] - d).days) <= 45}
                if len(candidates) == 1:
                    ad, src = candidates.pop(), "same-name Form 144 (plan link unverified)"
            if not ad or not d:
                flags.append(flag("R10B5-A", x, "UNKNOWN: transaction or unique plan adoption date unavailable", "UNKNOWN", "adoption date may be in issuer Item 408 disclosure"))
                continue
            if src.startswith("same-name"):
                flags.append(flag("R10B5-A", x, f"UNKNOWN: Form 144 lists adoption {ad.isoformat()} for a name match, but linkage to this transaction's plan is unverified", "UNKNOWN"))
                continue
            rel = x["relationship"].lower()
            if not rel or ";" in x["owner"] or ";" in rel:
                flags.append(flag("R10B5-A", x, "UNKNOWN: individual director/officer status cannot be established", "UNKNOWN"))
                continue
            if "director" in rel or "officer" in rel:
                if fpi or not issuer_type_known:
                    flags.append(flag("R10B5-A", x, "UNKNOWN: issuer type or relevant FPI results-bearing 6-K/20-F has not been verified", "UNKNOWN"))
                    continue
                results = next((p[1] for p in periodic if p[0] >= ad), None)
                if results is None:
                    flags.append(flag("R10B5-A", x, f"UNKNOWN: no 10-Q/10-K for the adoption quarter after {ad.isoformat()} in the index", "UNKNOWN"))
                    continue
                earliest = min(max(ad + dt.timedelta(days=90), add_business_days(results, 2)), ad + dt.timedelta(days=120))
                basis = f"later of adoption+90d and results filing {results.isoformat()}+2 business days, capped at adoption+120d"
            elif "10%owner" in rel or "other" in rel:
                earliest, basis = ad + dt.timedelta(days=30), "adoption+30d (persons other than issuer, directors, officers)"
            else:
                flags.append(flag("R10B5-A", x, "UNKNOWN: role does not establish the applicable cooling-off period", "UNKNOWN"))
                continue
            if d < earliest:
                flags.append(flag("R10B5-A", x, f"sale {x['date']} before earliest {earliest.isoformat()} ({basis}); adoption {ad.isoformat()} from {src}",
                                  "review candidate", "plan modification dates, checkbox is filing-level, plan identity, fiscal-quarter dating, exemptions"))
    # F144-A: notices versus possible same-name Form 4 sales (a notice is not an execution record)
    # A joint Form 4 reports the transaction once for several owners. It may
    # match a notice from one of them, but its shares cannot be attributed to
    # that person from this flat CSV row.
    sales = [([person_tokens(name) for name in x["owner"].split(";")], parse_date(x["date"]), x)
             for x in ledger if x["code"] == "S" and x["table"] == "non_derivative_transaction"
             and x["form"] in ("4", "4/A")]
    match_rows = []
    for n in f144:
        lo = (n["_filed"] or dt.date.min) - dt.timedelta(days=3) if n["_filed"] else None
        hi = (n["_sale"] + dt.timedelta(days=30)) if n["_sale"] else None
        hit = [x for owner_tokens, d, x in sales
               if d and lo and hi and lo <= d <= hi
               and any(same_person(tok, n["_tok"]) for tok in owner_tokens)
               and possibly_same_class(n.get("class_title", ""), x["security"])]
        hit = list({(x["accession"], x["date"], x["security"], x["shares"], x["price"]): x for x in hit}.values())
        hit_dates = [parse_date(x["date"]) for x in hit]
        known_shares = [finite_num(x["shares"]) for x in hit]
        amended_hit = any(x["owner_key"] in amended_owners for x in hit)
        joint_hit = any(not x["owner_key"] or ";" in x["owner"] for x in hit)
        match_rows.append({"notice_accession": n.get("accession", ""), "person": n.get("person", ""), "notice_filed": n.get("filed", ""), "units_to_sell": n.get("units_to_sell", ""),
                           "approx_sale_date": n.get("approx_sale_date", ""), "plan_adoption_date": n.get("plan_adoption_date", ""),
                           "matched_form4_sales": len(hit), "matched_shares": fmt(sum(known_shares), 0) if hit and not amended_hit and not joint_hit and all(v is not None for v in known_shares) else "",
                           "first_sale": min(hit_dates).isoformat() if hit_dates else "", "last_sale": max(hit_dates).isoformat() if hit_dates else "",
                           "status": ("UNKNOWN: possible same-person Form 4 sale(s) from same-name match; amendments need reconciliation" if amended_hit else
                                      "UNKNOWN: possible same-person Form 4 sale(s) on joint reports; seller and shares cannot be assigned" if joint_hit else
                                      "UNKNOWN: possible same-person Form 4 sale(s) from same-name match; identity and class unverified") if hit else
                                     ("no same-name, compatible-class Form 4 sale in matching window within this folder's coverage (not proof of no sale)" if lo and hi else "UNKNOWN: notice dates missing"),
                           "window": f"{lo}..{hi}" if lo and hi else "unknown (missing dates)"})
    out = rd / "digest"
    if out.is_symlink() or not out.resolve().is_relative_to(rd):
        fail("digest output directory escapes research folder")
    write_csv(out / "insider_ledger.csv", LEDGER_FIELDS, ledger)
    write_csv(out / "insider_flags.csv", ["rule_id", "owner", "accession", "event_date", "filed", "detail", "status", "false_positive_risks"], flags)
    write_csv(out / "form144_match.csv", ["notice_accession", "person", "notice_filed", "units_to_sell", "approx_sale_date", "plan_adoption_date", "matched_form4_sales", "matched_shares", "first_sale", "last_sale", "status", "window"], match_rows)
    write_atomic(out / "insider_summary.md", summary(rd, ledger, flags, match_rows, missing_inputs))
    print({"ledger_rows": len(ledger), "flags": len(flags), "form144_notices": len(match_rows)})


def summary(rd: Path, ledger: list[dict], flags: list[dict], m144: list[dict], missing_inputs: list[str] | None = None) -> str:
    agg = collections.defaultdict(lambda: collections.Counter())
    names = collections.defaultdict(set)
    owner_group = lambda x: x["owner_key"] or "joint:" + x["owner"]
    amended_owners = {owner_group(x) for x in ledger if x["form"].endswith("/A")}
    for x in ledger:
        if x["table"] != "non_derivative_transaction":
            continue
        sh, val = finite_num(x["shares"]), finite_num(x["value_usd"]) or 0
        owner_key = owner_group(x)
        key = (owner_key, x["security"] or "UNKNOWN security")
        names[owner_key].add(x["owner"])
        a = agg[key]
        # A derivative transaction's units are options/warrants, and an exercise
        # commonly has a second common-stock leg. Do not add those to stock shares.
        if sh is None or not x["security"]:
            a[x["category"] + "_shares_unknown"] += 1
        else:
            a[x["category"] + "_shares"] += sh
        a[x["category"] + "_usd"] += val
        a["rows"] += 1
        if x["code"] == "S":
            a["sale_rows"] += 1
            if x["value_usd"] != "":
                a["sale_usd_known_rows"] += 1
        if x["code"] == "S" and x["rule_10b5_1"] == "yes":
            if sh is None or not x["security"]:
                a["plan_sale_shares_unknown"] += 1
            else:
                a["plan_sale_shares"] += sh
    def shares_text(a: collections.Counter, category: str) -> str:
        return "unknown" if a[category + "_shares_unknown"] else f"{a[category + '_shares']:,.0f}"
    o = [f"# Insider summary: {rd.name}", "Built by scripts/build_insider_ledger.py. Ledger rows are Form 3/4/5 transaction lines; flags are review candidates, not findings.",
         f"{len(ledger)} ledger rows; flags: " + (", ".join(f"{k[0]} {k[1]} x{v}" for k, v in sorted(collections.Counter((f['rule_id'], f['status']) for f in flags).items())) or "none"),
         "", "## Open-market activity and other categories by owner and security (shares; USD estimated only when issuer reporting currency is USD)",
         "| owner | open-mkt buy sh | open-mkt sell sh | sell USD | sell sh on checkbox-marked 10b5-1 filings | award sh | tax-withhold sh | exercise sh |", "|---|---|---|---|---|---|---|---|"]
    if missing_inputs:
        o[3:3] = ["Coverage UNKNOWN: missing " + ", ".join(missing_inputs) + "; zero rows/notices do not prove no activity.", ""]
    display_names = {key: "; ".join(sorted(values, key=lambda s: (s.casefold(), s))) for key, values in names.items()}
    for key, a in sorted(agg.items(), key=lambda kv: (-kv[1]["open_market_sale_usd"], kv[0])):
        owner_key, security = key
        label = "joint report" if owner_key.startswith("joint:") else "CIK unavailable" if owner_key.startswith("name:") else f"CIK {owner_key}"
        owner = f"[{label}] {display_names[owner_key]} / {security}"
        safe_owner = clean_cell(owner, 180).replace("|", "\\|")
        if owner_key in amended_owners:
            o.append(f"| {safe_owner} | review amendments | review amendments | review amendments | review amendments | review amendments | review amendments | review amendments |")
            continue
        sell_usd = f"{a['open_market_sale_usd']:,.0f}" if a["sale_rows"] and a["sale_usd_known_rows"] == a["sale_rows"] else ("partial" if a["sale_usd_known_rows"] else "unknown")
        o.append(f"| {safe_owner} | {shares_text(a, 'open_market_purchase')} | {shares_text(a, 'open_market_sale')} | {sell_usd} | {shares_text(a, 'plan_sale')} | {shares_text(a, 'award_grant')} | {shares_text(a, 'tax_withholding')} | {shares_text(a, 'derivative_exercise_conversion')} |")
    if amended_owners:
        o += ["Totals suppressed for owners with amended Forms 4/5: the cache does not identify which original transaction lines were replaced."]
    unm = sum(1 for m in m144 if m["status"].startswith("no same-name"))
    o += ["Derivative option and warrant units are excluded from the share columns. The 10b5-1 checkbox applies to the filing, not necessarily every sale row; UNKNOWN checkboxes are excluded.",
          "USD values assume the transaction price currency matches the issuer's USD reporting currency; verify material amounts in the filing.",
          "", f"## Form 144 notices: {len(m144)}; with no same-name, compatible-class Form 4 sale in the matching window: {unm}",
          "A notice is a proposed-sale filing, not an execution record; name matches do not prove identity or security class, and 'no match' means none in this folder's coverage.", "",
          "## Flags (see insider_flags.csv for every row)"]
    for f in flags[:40]:
        o.append(f"- {f['rule_id']} [{f['status']}] {clean_cell(f['owner'], 100)} {clean_cell(f['event_date'], 40)}: {clean_cell(f['detail'], 300)}")
    if len(flags) > 40:
        o.append(f"- ... {len(flags) - 40} more in insider_flags.csv")
    return "\n".join(o) + "\n"


if __name__ == "__main__":
    main()
