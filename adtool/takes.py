"""Bring the narrator's recorded takes into the cue sheet.

Two ways to record:
  * one file per cue, named with the cue id first:  takes/0045.wav, takes/0046 church.wav ...
  * one long file with a pause of at least a second between lines, read in cue order;
    the tool splits it on silence and matches segments to cues in order.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import audio as A
from .config import Config
from .cues import Cue, CueSheet
from .media import convert_audio
from .timecode import fmt_short

AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".ogg"}


def _store(cfg: Config, cue: Cue, mono, sr: int) -> Path:
    mono = A.trim_silence(mono, sr)
    mono = A.normalize_voice(mono, float(cfg.get("audio", "voice_rms_db", default=-20.0)),
                             float(cfg.get("audio", "voice_peak_db", default=-3.0)))
    dst = cfg.work / "takes" / f"{cue.id:04d}.wav"
    A.write(dst, mono, sr)
    cue.clip = cfg.rel(dst)
    cue.measured_s = round(len(mono) / sr, 2)
    cue.measure = "take"
    if cue.status != "skip":
        cue.status = "recorded"
    cue.recompute_fit()
    return dst


def _load_mono(cfg: Config, src: Path) -> Tuple:
    sr = int(cfg.get("audio", "sr", default=48000))
    tmp = cfg.work / "takes" / "_src" / (src.stem + ".wav")
    convert_audio(src, tmp, sr, 1, cfg)
    data, _ = A.read(tmp)
    return A.to_mono(data), sr


def import_dir(cfg: Config, sheet: CueSheet, folder: Path) -> List[str]:
    log: List[str] = []
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in AUDIO_EXT:
            continue
        m = re.match(r"\s*(\d+)", f.stem)
        if not m:
            log.append(f"skipped {f.name}: file name must start with the cue id")
            continue
        try:
            cue = sheet.by_id(int(m.group(1)))
        except Exception:
            log.append(f"skipped {f.name}: no cue #{m.group(1)}")
            continue
        mono, sr = _load_mono(cfg, f)
        _store(cfg, cue, mono, sr)
        log.append(f"#{cue.id} <- {f.name}  {cue.measured_s:.1f}s window {cue.window_s:.1f}s fit={cue.fits}")
    sheet.save()
    return log


def import_long_take(cfg: Config, sheet: CueSheet, src: Path, targets: Sequence[Cue],
                     order: Optional[List[int]] = None) -> Dict:
    t = cfg.data.get("takes", {})
    mono, sr = _load_mono(cfg, src)
    segs = A.split_on_silence(mono, sr, float(t.get("split_silence_s", 1.0)),
                              float(t.get("split_threshold_db", -40.0)), float(t.get("min_take_s", 0.3)))
    targets = [c for c in targets if c.status != "skip" and c.line.strip()]
    report: Dict = {"segments": len(segs), "expected": len(targets), "assigned": [], "ok": False}
    ids = order if order else [c.id for c in targets]
    if order is None and len(segs) != len(targets):
        L = [f"# Takes report: {src.name}", "",
             f"Found {len(segs)} spoken segments but expected {len(targets)} lines "
             f"(cues {targets[0].id if targets else '?'}–{targets[-1].id if targets else '?'}).", "",
             "Either re-record the range, adjust takes.split_silence_s / split_threshold_db in ad.config.json, "
             "or write an order file (one cue id per segment, in order; use 0 to drop a segment) and rerun with --order.", "",
             "| seg | start | end | length |", "|---|---|---|---|"]
        for k, (a, b) in enumerate(segs, 1):
            L.append(f"| {k} | {fmt_short(a)} | {fmt_short(b)} | {b - a:.1f}s |")
        rep = cfg.out / "takes_report.md"
        rep.write_text("\n".join(L) + "\n", encoding="utf-8")
        report["report"] = rep
        return report
    if order is not None and len(order) != len(segs):
        raise SystemExit(f"order file lists {len(order)} ids but the recording has {len(segs)} segments")
    for (a, b), cid in zip(segs, ids):
        if cid == 0:
            continue
        cue = sheet.by_id(cid)
        _store(cfg, cue, mono[int(a * sr):int(b * sr)], sr)
        report["assigned"].append(f"#{cue.id} {fmt_short(cue.start_s)}  {cue.measured_s:.1f}s / window {cue.window_s:.1f}s  fit={cue.fits}")
    sheet.save()
    report["ok"] = True
    return report
