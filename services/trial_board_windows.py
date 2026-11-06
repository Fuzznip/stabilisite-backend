"""Backend validation of dated availability, including timezone/DST rules."""
from datetime import datetime, timezone
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

class RuleError(ValueError):
    pass


def parse_windows(text, zone, now=None):
    """One `YYYY-MM-DD HH:MM / YYYY-MM-DD HH:MM` window per line.

An explicit UTC offset can disambiguate fall-back times. Reject spring gaps.
"""
    now = int(time.time()) if now is None else now
    try:
        tz = ZoneInfo(zone.strip())
    except ZoneInfoNotFoundError:
        raise RuleError("Use an IANA timezone, e.g. America/New_York or Europe/London.")

    def instant(value):
        try:
            dt = datetime.fromisoformat(value.strip())
        except ValueError:
            raise RuleError("Use YYYY-MM-DD HH:MM / YYYY-MM-DD HH:MM, one window per line.")
        if dt.tzinfo:
            local = dt.astimezone(tz)
            if local.replace(tzinfo=None) != dt.replace(tzinfo=None):
                raise RuleError("That UTC offset does not match the named timezone.")
            return int(dt.timestamp())
        candidates = set()
        for fold in (0, 1):
            aware = dt.replace(tzinfo=tz, fold=fold)
            if aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) == dt:
                candidates.add(int(aware.timestamp()))
        if len(candidates) != 1:
            raise RuleError("That local time is ambiguous or does not exist (DST). Include its UTC offset.")
        return candidates.pop()

    result = []
    for line in text.strip().splitlines():
        parts = line.split(" / ")
        if len(parts) != 2:
            raise RuleError("Separate start and end with ' / '.")
        start, end = map(instant, parts)
        if not now + 300 <= start < end <= now + 21 * 86400:
            raise RuleError("Choose future windows at least 5 minutes away and within the next 21 days.")
        if end - start > 12 * 3600:
            raise RuleError("Each window must be at most 12 hours.")
        result.append([start, end])
    if not 1 <= len(result) <= 5:
        raise RuleError("Provide 1–5 windows (2–3 is ideal).")
    result.sort()
    if any(a[1] > b[0] for a, b in zip(result, result[1:])):
        raise RuleError("Availability windows must not overlap.")
    return result

