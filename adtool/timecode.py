"""Timecode parsing and formatting.

Accepted inputs: "83", "83.2", "1:23", "01:23.5", "1:02:03.456", "00:01:23,456".
Output format is always hh:mm:ss.mmm so it sorts and reads consistently.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Set, Tuple


def parse_tc(value) -> float:
    """Return seconds as a float for a timecode string or number."""
    if value is None:
        raise ValueError("empty timecode")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        raise ValueError("empty timecode")
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(f"bad timecode: {value!r}")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"bad timecode: {value!r}") from None
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60.0 + n
    return seconds


def fmt_tc(seconds: float, ms: bool = True) -> str:
    """Format seconds as hh:mm:ss.mmm (or hh:mm:ss when ms=False)."""
    neg = seconds < 0
    total_ms = int(round(abs(seconds) * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    out = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    if ms:
        out += f".{millis:03d}"
    return ("-" if neg else "") + out


def fmt_short(seconds: float) -> str:
    """Compact m:ss.s style used in reports (drops the hour when zero)."""
    tc = fmt_tc(seconds)
    if tc.startswith("00:"):
        tc = tc[3:]
    return tc


def fmt_srt(seconds: float) -> str:
    return fmt_tc(seconds).replace(".", ",")


def parse_range(text: Optional[str], duration: Optional[float] = None) -> Tuple[float, Optional[float]]:
    """Parse "0:00-5:00", "5:00-", "-5:00" or "all" into (start, end) seconds."""
    text = (text or "").strip()
    if text in ("", "all"):
        return 0.0, duration
    if "-" not in text:
        raise ValueError("a range looks like 0:00-5:00 (start-end)")
    a, b = text.split("-", 1)
    start = parse_tc(a) if a.strip() else 0.0
    end = parse_tc(b) if b.strip() else duration
    if end is not None and end <= start:
        raise ValueError("range end must come after the start")
    return start, end


def parse_ids(text: Optional[str]) -> Set[int]:
    """Parse "12-30,45,50" into a set of integer ids."""
    ids: Set[int] = set()
    for chunk in (text or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", chunk)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if hi < lo:
                lo, hi = hi, lo
            ids.update(range(lo, hi + 1))
        else:
            ids.add(int(chunk))
    return ids


def range_label(start: float, end: Optional[float]) -> str:
    """File-name safe label like 0000-0500 (minutes+seconds) for a range."""
    def part(t: Optional[float]) -> str:
        if t is None:
            return "end"
        m, s = divmod(int(round(t)), 60)
        return f"{m:02d}{s:02d}"
    return f"{part(start)}-{part(end)}"
