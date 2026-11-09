"""Date/time helpers with timezone support."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    return utcnow().isoformat(timespec="seconds")


def parse_datetime(value: object, default_tz: str = "Europe/Kyiv") -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz(default_tz))
        return dt
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    raw = str(value).strip()
    if not raw:
        return None

    # RFC 822 (RSS)
    if "," in raw and any(month in raw for month in ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")):
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (TypeError, ValueError):
            pass

    iso = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz(default_tz))
        return dt
    except ValueError:
        pass

    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=_tz(default_tz))
        except ValueError:
            continue
    return None


def parse_relative_date(value: str, default_tz: str = "Europe/Kyiv") -> datetime | None:
    raw = (value or "").strip().casefold()
    if not raw:
        return None
    now = datetime.now(_tz(default_tz))
    if raw in {"сьогодні", "сегодня", "today", "щойно", "только что"}:
        return now
    if raw in {"вчора", "вчера", "yesterday"}:
        return now - timedelta(days=1)
    if "хвилин" in raw or "минут" in raw:
        return now - timedelta(minutes=5)
    if "годин" in raw or "час" in raw:
        return now - timedelta(hours=1)
    return parse_datetime(value, default_tz)


def to_local(dt: datetime | None, tz_name: str = "Europe/Kyiv") -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_tz(tz_name))


def human_time(dt: datetime | None, tz_name: str = "Europe/Kyiv") -> str:
    if dt is None:
        return "—"
    local = to_local(dt, tz_name)
    now = datetime.now(_tz(tz_name))
    if local is None:
        return "—"
    delta = now - local
    seconds = int(delta.total_seconds())
    if 0 <= seconds < 60:
        return "щойно"
    if 0 <= seconds < 3600:
        return f"{seconds // 60} хв тому"
    if local.date() == now.date():
        return f"сьогодні {local:%H:%M}"
    if local.date() == now.date() - timedelta(days=1):
        return f"вчора {local:%H:%M}"
    return f"{local:%d.%m.%Y %H:%M}"


def human_date(dt: datetime | None, tz_name: str = "Europe/Kyiv") -> str:
    local = to_local(dt, tz_name)
    return f"{local:%d.%m.%Y}" if local else "—"


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def today_utc_iso() -> str:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat(timespec="seconds")
