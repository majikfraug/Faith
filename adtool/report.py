"""Progress reports and the recording script."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from .config import Config
from .cues import Cue, CueSheet
from .timecode import fmt_short


def status_markdown(cfg: Config, sheet: CueSheet, block_s: float = 300.0) -> str:
    s = sheet.summary()
    L: List[str] = [f"# Status: {cfg.get('project_name', default='Film')}", ""]
    L.append(f"Cues: {s['total']}  (" + ", ".join(f"{k} {v}" for k, v in sorted(s['by_type'].items())) + ")")
    L.append("Status: " + ", ".join(f"{k} {v}" for k, v in sorted(s['by_status'].items())))
    L.append("Fit: " + ", ".join(f"{k} {v}" for k, v in sorted(s['by_fits'].items())))
    L.append(f"Description time available: {s['desc_seconds']:.0f}s in DESC windows; "
             f"subtitles estimated too long for their window: {s['sub_est_no']}")
    L.append("")
    L.append("| block | cues | new | drafted | approved | recorded | skip | fit=no |")
    L.append("|---|---|---|---|---|---|---|---|")
    end = sheet.duration_hint()
    next_range: Optional[str] = None
    b = 0.0
    while b < end:
        blk = [c for c in sheet.cues if b <= c.start_s < b + block_s]
        if blk:
            counts = {k: sum(1 for c in blk if c.status == k) for k in ("new", "drafted", "approved", "recorded", "skip")}
            no = sum(1 for c in blk if c.fits == "no" and c.status != "skip")
            L.append(f"| {fmt_short(b)}–{fmt_short(min(b + block_s, end))} | {len(blk)} | {counts['new']} | {counts['drafted']} | "
                     f"{counts['approved']} | {counts['recorded']} | {counts['skip']} | {no} |")
            if next_range is None and counts["new"] > 0:
                next_range = f"{fmt_short(b)}-{fmt_short(min(b + block_s, end))}"
        b += block_s
    L.append("")
    L.append(f"Next range to draft: {next_range}" if next_range else "All blocks have been drafted.")
    return "\n".join(L) + "\n"


def recording_script(cfg: Config, sheet: CueSheet, cues: Optional[Sequence[Cue]] = None) -> str:
    cues = [c for c in (cues if cues is not None else sheet.cues) if c.status != "skip" and c.line.strip()]
    L: List[str] = [f"# Recording script: {cfg.get('project_name', default='Film')}", ""]
    L.append("How to record in one pass: read each line, then stay silent for at least two seconds before the next one. "
             "Do not read the cue numbers aloud. If you flub a line, pause two seconds and read it again; "
             "then tell Claude which cue to keep. Keep the pace natural; the 'max' time is the window you must fit.")
    L.append("")
    glossary = cfg.project / "glossary.md"
    if glossary.exists():
        L.append("## Names and pronunciations (from project/glossary.md)\n")
        L.append(glossary.read_text(encoding="utf-8").strip())
        L.append("")
    L.append("## Lines\n")
    for c in cues:
        tag = {"SUB": "subtitle", "TEXT": "on-screen text", "DESC": "description"}[c.type]
        L.append(f"{c.id:04d}  {fmt_short(c.start_s)}  max {c.window_s:.1f}s  ({tag})")
        L.append(f"      {c.line}")
        L.append("")
    return "\n".join(L) + "\n"
