"""
Conversion entre fuseaux horaires pour la programmation des campagnes.
En base, les dates sont toujours stockées en UTC (naive).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def to_utc(local_dt: datetime, tz_name: str) -> datetime:
    """
    Convertit une datetime locale (naive) dans un fuseau tz_name
    vers UTC (naive).
    """
    if local_dt.tzinfo is None:
        try:
            tz = ZoneInfo(tz_name or "UTC")
        except Exception:
            tz = ZoneInfo("UTC")
        local_dt = local_dt.replace(tzinfo=tz)
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None)


def from_utc(utc_dt: datetime, tz_name: str) -> datetime:
    """Convertit une datetime UTC (naive) vers un fuseau tz_name (naive local)."""
    if utc_dt is None:
        return None
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    return utc_dt.astimezone(tz).replace(tzinfo=None)