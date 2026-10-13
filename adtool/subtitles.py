"""Subtitle parsing for .srt and .vtt files (including YouTube caption exports)."""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

from .timecode import parse_tc

ARROW_RE = re.compile(r"(?P<a>[\d:.,]+)\s*-->\s*(?P<b>[\d:.,]+)")
TAG_RE = re.compile(r"<[^>]+>")
ASS_TAG_RE = re.compile(r"\{\\[^}]*\}")
SPACE_RE = re.compile(r"\s+")


@dataclass
class Subtitle:
    index: int
    start: float
    end: float
    text: str


def clean_text(raw: str) -> str:
    text = TAG_RE.sub("", raw)
    text = ASS_TAG_RE.sub("", text)
    text = html.unescape(text)
    text = text.replace("​", "")
    text = SPACE_RE.sub(" ", text).strip()
    return text


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_subtitles(path: str | Path) -> List[Subtitle]:
    """Parse an SRT or WebVTT file into a time-sorted list of subtitles."""
    path = Path(path)
    content = _read_text(path)
    looks_auto = "<c>" in content or re.search(r"<\d{2}:\d{2}", content) is not None

    subs: List[Subtitle] = []
    lines = content.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        m = ARROW_RE.search(lines[i])
        if not m:
            i += 1
            continue
        try:
            start = parse_tc(m.group("a"))
            end = parse_tc(m.group("b"))
        except ValueError:
            i += 1
            continue
        i += 1
        text_lines = []
        while i < n and lines[i].strip() != "":
            if ARROW_RE.search(lines[i]):
                break
            text_lines.append(lines[i])
            i += 1
        text = clean_text(" ".join(text_lines))
        if text and end > start:
            subs.append(Subtitle(len(subs) + 1, start, end, text))

    subs.sort(key=lambda s: (s.start, s.end))

    if looks_auto:
        subs = _clean_auto_captions(subs)

    for k, s in enumerate(subs, 1):
        s.index = k
    return subs


def _clean_auto_captions(subs: List[Subtitle]) -> List[Subtitle]:
    """YouTube auto captions repeat the previous line in each cue; undo that."""
    out: List[Subtitle] = []
    for s in subs:
        if s.end - s.start < 0.05:
            continue
        if out:
            prev = out[-1]
            if s.text == prev.text:
                prev.end = max(prev.end, s.end)
                continue
            if s.text.startswith(prev.text + " "):
                s.text = s.text[len(prev.text):].strip()
        if s.text:
            out.append(s)
    return out


def save_json(subs: List[Subtitle], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps([asdict(s) for s in subs], indent=1, ensure_ascii=False), encoding="utf-8")


def load_json(path: str | Path) -> List[Subtitle]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Subtitle(**d) for d in data]
