import re

_DURATION_RE = re.compile(
    r"(\d+)\s*(weeks?|wks?|w|days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)(?![a-z])", re.IGNORECASE
)
_UNIT_SECONDS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_duration(text: str) -> int | None:
    """Parses '10m', '2h30m', '1d', '1w 2d', '10 minutes', '1 day and 2 hours' into seconds. None if invalid."""
    text = (text or "").strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text) * 60  # bare number = minutes
    matches = _DURATION_RE.findall(text)
    leftover = re.sub(r"\b(and)\b|[,\s]", "", _DURATION_RE.sub("", text))
    if not matches or leftover:
        return None
    # "wks"/"mins"/"hrs"... -> first letter is the unit ("m" = minutes; months aren't supported)
    return sum(int(n) * _UNIT_SECONDS[u[0].lower()] for n, u in matches)


def xp_for_level(level: int) -> int:
    """XP needed to go from `level` to `level + 1`."""
    return 5 * level * level + 50 * level + 100
