from datetime import datetime, timezone
def utcnow(): return datetime.now(timezone.utc)
def now(): return datetime.now(timezone.utc).astimezone()
def parse_datetime(s):
    try: return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception: return None
def as_local(d): return d.astimezone()
def as_utc(d): return d.astimezone(timezone.utc)
DEFAULT_TIME_ZONE = timezone.utc
