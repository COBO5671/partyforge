"""Event form dates are wall-clock times in the event's timezone."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def event_zone(event):
    try:
        return ZoneInfo(event.timezone or "America/Chicago")
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Chicago")


def event_now(event):
    return datetime.now(event_zone(event)).replace(tzinfo=None)
