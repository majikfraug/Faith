"""Adobe Audition marker export.

Audition imports markers from a text file (Markers panel menu, or File > Import > Markers).
Its own export is tab-separated with the columns below and "decimal" times (m:ss.sss).
Adobe does not document the format and it varies by version, so if an import is
refused, export two markers from your Audition and pass that file as --like: the
writer then copies its delimiter, column names and time style exactly.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .cues import Cue

DEFAULT_HEADER = ["Name", "Start", "Duration", "Time Format", "Type", "Description"]


def _fmt(t: float, style: str, sr: int, fps: float) -> str:
    if style == "samples":
        return str(int(round(t * sr)))
    if style == "seconds":
        return f"{t:.3f}"
    if style == "frames":
        h, rem = divmod(int(t), 3600)
        m, s = divmod(rem, 60)
        f = int(round((t - int(t)) * fps))
        return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
    if style == "hmmss":
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h)}:{int(m):02d}:{s:06.3f}"
    m, s = divmod(t, 60)  # decimal m:ss.sss (minutes keep counting past 59)
    return f"{int(m)}:{s:06.3f}"


def _detect_style(sample: str) -> str:
    s = sample.strip()
    if re.fullmatch(r"\d+", s):
        return "samples"
    if re.fullmatch(r"\d+\.\d+", s):
        return "seconds"
    if re.fullmatch(r"\d+:\d{2}:\d{2}:\d{2}", s):
        return "frames"
    if re.fullmatch(r"\d+:\d{2}:\d{2}[.,]\d+", s):
        return "hmmss"
    return "decimal"


def _read_template(path: Path) -> Dict:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("template file is empty")
    delim = "\t" if "\t" in lines[0] else ","
    header = next(csv.reader([lines[0]], delimiter=delim))
    sample = next(csv.reader([lines[1]], delimiter=delim)) if len(lines) > 1 else []
    row = dict(zip(header, sample))
    lower = {h.lower(): h for h in header}
    start_col = lower.get("start")
    style = _detect_style(row.get(start_col, "")) if start_col and row.get(start_col) else "decimal"
    token = row.get(lower.get("time format", ""), "decimal") or "decimal"
    mtype = row.get(lower.get("type", ""), "Cue") or "Cue"
    return {"delim": delim, "header": header, "style": style, "token": token, "type": mtype}


def write_audition(cues: Sequence[Cue], path: Path, like: Optional[Path] = None, sr: int = 48000, fps: float = 30.0) -> Path:
    if like:
        tpl = _read_template(Path(like))
    else:
        tpl = {"delim": "\t", "header": DEFAULT_HEADER, "style": "decimal", "token": "decimal", "type": "Cue"}
    header = tpl["header"]
    lower = {h.lower(): h for h in header}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=tpl["delim"], lineterminator="\n")
        w.writerow(header)
        for c in sorted(cues, key=lambda c: c.start_s):
            if c.status == "skip":
                continue
            desc = " ".join((c.line or c.source_text).split()).replace("\t", " ")
            values = {
                "name": f"{c.id:04d} {c.type}",
                "start": _fmt(c.start_s, tpl["style"], sr, fps),
                "duration": _fmt(c.window_s, tpl["style"], sr, fps),
                "time format": tpl["token"],
                "type": tpl["type"],
                "description": desc,
            }
            w.writerow([values.get(h.lower(), "") for h in header])
    return path
