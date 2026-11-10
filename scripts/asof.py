"""Point-in-time (as-of) helpers shared by fetch_company.py and agent_fetch.py.

An as-of run builds a separate research folder (research/<TICKER>_asof_<UTC stamp>/) with script outputs
filtered by documented availability rules. Agent-gathered sources need separate checks. Rules in INVENTORY.md:
- SEC filings: accepted (acceptanceDateTime) at or before the cutoff; date-only records count as accepted at the end of
  their filing day, New York time.
- XBRL company facts: a fact is available if its filing date is before the cutoff's New York date, or on that date with a
  known acceptance time at or before the cutoff.
- Daily prices: a session's close counts as known CLOSE_LAG_MIN minutes after 16:00 New York time.
- FINRA short interest: settlement dates at least SI_LAG_DAYS before the cutoff (assumed publication lag, not verified).
- Treasury par yield curve: a row counts as published at 18:00 New York time on its date.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
CLOSE_LAG_MIN = 5
SI_LAG_DAYS = 14
TREASURY_PUBLISH_HOUR_NY = 18


def parse_as_of(text: str, tz: str | None = None) -> dt.datetime:
    """Return the cutoff as an aware UTC datetime. A time is required: the cutoff is an exact instant."""
    text = text.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError("--as-of needs a time as well as a date, for example '2026-10-29 16:00' (it is an exact instant)")
    zone = None
    if tz:
        try:
            zone = ZoneInfo(tz)  # validate --tz even when the input includes an offset
        except ZoneInfoNotFoundError as e:
            raise ValueError(f"unknown --tz: {tz}") from e
    when = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if when.second or when.microsecond:
        raise ValueError("--as-of must have minute precision (folder names identify minutes)")
    if when.tzinfo is None:
        if zone is None:
            raise ValueError("a time without a UTC offset needs --tz (for example --tz America/New_York): the cutoff must be an unambiguous instant")
        candidates = [when.replace(tzinfo=zone, fold=fold) for fold in (0, 1)]
        valid = [c for c in candidates if c.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == when]
        if not valid:
            raise ValueError("--as-of is a nonexistent local time; give a UTC offset")
        if len(valid) == 2 and valid[0].utcoffset() != valid[1].utcoffset():
            raise ValueError("--as-of is an ambiguous local time; give a UTC offset")
        when = valid[0]
    return when.astimezone(UTC)


def stamp(asof_utc: dt.datetime) -> str:
    return asof_utc.strftime("%Y%m%dT%H%MZ")


def ny_date(asof_utc: dt.datetime) -> dt.date:
    return asof_utc.astimezone(NY).date()


def acceptance_utc(row: dict) -> dt.datetime:
    """SEC acceptance instant; without one, the end of the filing day in New York."""
    raw = (row.get("acceptanceDateTime") or "").strip()
    if raw:
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(UTC)
        except ValueError:
            pass
    day = dt.date.fromisoformat(row["filingDate"])
    return dt.datetime.combine(day, dt.time(23, 59, 59), tzinfo=NY).astimezone(UTC)


def close_available_utc(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(16, CLOSE_LAG_MIN), tzinfo=NY).astimezone(UTC)


def truncate_price_csv(src: Path, dst: Path, asof_utc: dt.datetime) -> tuple[int, int, str | None]:
    """Finviz daily history (Date as MM/DD/YYYY): keep sessions whose close was known at the cutoff."""
    kept, dropped, last = 0, 0, None
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open(newline="") as fin, dst.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            day = dt.datetime.strptime(row["Date"], "%m/%d/%Y").date()
            if close_available_utc(day) <= asof_utc:
                writer.writerow(row)
                kept += 1
                last = day.isoformat()
            else:
                dropped += 1
    return kept, dropped, last


def truncate_si_csv(src: Path, dst: Path, asof_utc: dt.datetime, lag_days: int = SI_LAG_DAYS) -> tuple[int, int, str | None]:
    """Finviz short-interest history (Settlement Date as YYYY-MM-DD): settlement at least lag_days before the cutoff date."""
    limit = ny_date(asof_utc) - dt.timedelta(days=lag_days)
    kept, dropped, last = 0, 0, None
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open(newline="") as fin, dst.open("w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            day = dt.date.fromisoformat(row["Settlement Date"])
            if day <= limit:
                writer.writerow(row)
                kept += 1
                last = last or day.isoformat()  # newest first in the source
            else:
                dropped += 1
    return kept, dropped, last


def fact_available(fact: dict, asof_utc: dt.datetime, acc_accept: dict[str, dt.datetime]) -> bool:
    filed = fact.get("filed")
    if not filed:
        return False
    try:
        day = dt.date.fromisoformat(filed)
    except ValueError:
        return False
    cutoff_day = ny_date(asof_utc)
    accepted = acc_accept.get(fact.get("accn", ""))
    if accepted is not None:
        return day <= cutoff_day and accepted <= asof_utc
    # An accession outside the available index has only a date, never an acceptance instant.
    return day < cutoff_day


def filter_companyfacts(data: dict, asof_utc: dt.datetime, acc_accept: dict[str, dt.datetime]) -> tuple[dict, dict]:
    """Keep only XBRL facts that were available at the cutoff. Returns (filtered, {'kept': n, 'dropped': n})."""
    kept = dropped = 0
    out = {k: v for k, v in data.items() if k != "facts"}
    out["facts"] = {}
    for taxonomy, tags in (data.get("facts") or {}).items():
        new_tags = {}
        for tag, body in tags.items():
            new_units = {}
            for unit, facts in (body.get("units") or {}).items():
                good = [{k: v for k, v in f.items() if k != "frame"} for f in facts
                        if fact_available(f, asof_utc, acc_accept)]
                kept += len(good)
                dropped += len(facts) - len(good)
                if good:
                    new_units[unit] = good
            if new_units:
                new_tags[tag] = {"units": new_units}  # labels/descriptions can change in later submissions
        if new_tags:
            out["facts"][taxonomy] = new_tags
    return out, {"kept": kept, "dropped": dropped}


def treasury_available(day: dt.date, asof_utc: dt.datetime) -> bool:
    return dt.datetime.combine(day, dt.time(TREASURY_PUBLISH_HOUR_NY, 0), tzinfo=NY).astimezone(UTC) <= asof_utc
