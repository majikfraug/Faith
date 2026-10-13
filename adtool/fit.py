"""Measure whether each line fits its window, using TTS (or a word-rate estimate)."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import audio as A
from . import tts
from .config import Config
from .cues import Cue, CueSheet
from .timecode import fmt_short


def run_fit(cfg: Config, sheet: CueSheet, cues: Sequence[Cue], engine: Optional[str] = None,
            estimate_only: bool = False) -> Dict:
    wps = sheet.wps
    used_engine = "estimate"
    tts_dead = estimate_only
    measured = 0
    for c in cues:
        if c.status == "skip" or not c.line.strip():
            continue
        if c.measure == "take" and c.clip and cfg.abs(c.clip).exists():
            dur = A.duration(cfg.abs(c.clip))
        elif tts_dead:
            dur = c.est_s(wps)
            c.measure = "est"
        else:
            try:
                path, used = tts.synth(cfg, c.line, engine)
                dur = tts.measure(path)
                c.measure = "tts"
                used_engine = used
            except tts.TTSError as e:
                print(f"  TTS unavailable ({e}); using word-rate estimates from here on")
                tts_dead = True
                dur = c.est_s(wps)
                c.measure = "est"
        c.measured_s = round(dur, 2)
        c.recompute_fit()
        measured += 1
    sheet.save()

    problems = [c for c in cues if c.fits in ("no", "tight") and c.status != "skip"]
    problems.sort(key=lambda c: (0 if c.fits == "no" else 1, c.start_s))
    L: List[str] = ["# Fit report", "", f"Measured {measured} cue(s) with: {used_engine}. "
                    f"Rate for estimates: {wps} words/s.", ""]
    if not problems:
        L.append("Everything measured fits its window.")
    else:
        L.append(f"{sum(1 for c in problems if c.fits == 'no')} do not fit, "
                 f"{sum(1 for c in problems if c.fits == 'tight')} are tight (they spill into slack before the next speech).")
        L.append("")
        L.append("| id | type | start | window | measured | over | cut ≈ words | line |")
        L.append("|---|---|---|---|---|---|---|---|")
        for c in problems:
            over = c.overage_s()
            cut = int(math.ceil(over * wps))
            L.append(f"| {c.id} | {c.type} | {fmt_short(c.start_s)} | {c.window_s:.1f}s | {c.measured_s:.1f}s | "
                     f"{over:.1f}s | {cut} | {c.line.replace('|', '/')} |")
    report = cfg.out / "fit_report.md"
    report.write_text("\n".join(L) + "\n", encoding="utf-8")
    return {"measured": measured, "engine": used_engine, "no": sum(1 for c in problems if c.fits == "no"),
            "tight": sum(1 for c in problems if c.fits == "tight"), "report": report, "problems": problems}
