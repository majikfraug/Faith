"""Build the review package and the final YouTube track."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import audio as A
from . import tts
from .config import Config
from .cues import CueSheet
from .markers import write_audition
from .media import encode_aac, mux_review, probe
from .report import recording_script
from .speech import ensure_mix_audio, ensure_stem_audio
from .timecode import fmt_short


def build(cfg: Config, sheet: CueSheet, final: bool = False, allow_tts: bool = True, with_video: bool = True,
          like: Optional[Path] = None, engine: Optional[str] = None) -> Dict:
    sr = int(cfg.get("audio", "sr", default=48000))
    ch = int(cfg.get("audio", "channels", default=2))
    subtype = cfg.get("audio", "subtype", default="PCM_16")
    duck = cfg.data.get("duck", {})
    lead = float(cfg.get("timing", "sub_lead_s", default=0.3))

    mix_src = ensure_mix_audio(cfg)
    total_s = A.duration(mix_src)
    # With a dialogue stem and a music stem (effects optional) the mix is built from stems: only the dialogue
    # is ducked under the reads, so music and effects never pump. Otherwise the film's full mix is ducked.
    media = cfg.media_files()
    stems: Dict[str, Path] = {}
    if media["dialogue"] is not None and media["music"] is not None:
        stems = {k: ensure_stem_audio(cfg, k) for k in ("dialogue", "music", "effects") if media[k] is not None}

    placements: List[Dict] = []
    duck_spans: List[Tuple[float, float, float]] = []
    missing: List[str] = []
    takes_used = tts_used = 0
    tts_dead = not allow_tts
    placed = []
    for c in sorted(sheet.cues, key=lambda c: c.start_s):
        if c.status == "skip" or not c.line.strip():
            continue
        clip: Optional[Path] = None
        if c.measure == "take" and c.clip and cfg.abs(c.clip).exists():
            clip = cfg.abs(c.clip)
            takes_used += 1
        elif not tts_dead:
            try:
                clip, _ = tts.synth(cfg, c.line, engine)
                tts_used += 1
            except tts.TTSError as e:
                print(f"  TTS unavailable ({e}); cues without takes will be left out")
                tts_dead = True
        if clip is None:
            missing.append(f"#{c.id} {fmt_short(c.start_s)} {c.type}")
            continue
        start = c.start_s + (lead if c.type == "SUB" else 0.0)
        dur = A.duration(clip)
        placements.append({"start": start, "path": clip, "gain": 1.0})
        duck_spans.append((start, start + dur, float(duck.get(c.type, -7.0))))
        placed.append((c, start, start + dur))

    collisions: List[str] = []
    for (c1, s1, e1), (c2, s2, e2) in zip(placed, placed[1:]):
        if e1 > s2 + 0.02:
            collisions.append(f"#{c1.id} runs {e1 - s2:.1f}s into #{c2.id} at {fmt_short(s2)}")

    out = cfg.out
    stem = out / "stem.wav"
    stats_stem = A.render(total_s, sr, ch, placements, stem, subtype=subtype)
    if final:
        mix_dir = out / "final"
        mix_dir.mkdir(parents=True, exist_ok=True)
        mix = mix_dir / "youtube_descriptive_audio.wav"
    else:
        mix = out / "mix_review.wav"
    ramp = float(duck.get("ramp_s", 0.25))
    if stems:
        music_db = float(duck.get("MUSIC", 0.0))
        bed_spans = [(a, b, music_db) for a, b, _ in duck_spans] if music_db < 0 else None
        gain = A.db_to_gain(float(cfg.get("audio", "stems_gain_db", default=0.0)))
        layers = [{"path": stems["dialogue"], "duck_spans": duck_spans, "gain": gain}]
        layers += [{"path": stems[k], "duck_spans": bed_spans, "gain": gain} for k in ("music", "effects") if k in stems]
        stats_mix = A.render(total_s, sr, ch, placements, mix, backgrounds=layers, ramp_s=ramp, subtype=subtype)
    else:
        stats_mix = A.render(total_s, sr, ch, placements, mix, background=mix_src, duck_spans=duck_spans,
                             ramp_s=ramp, subtype=subtype)
    results: Dict = {"stem": stem, "mix": mix, "takes": takes_used, "tts": tts_used, "missing": missing,
                     "collisions": collisions, "clipped": stats_mix["clipped_samples"], "peak_db": stats_mix["peak_db"],
                     "stems": sorted(stems)}
    if final:
        results["m4a"] = encode_aac(mix, mix.with_suffix(".m4a"), cfg)

    video = cfg.media_files()["video"]
    if with_video and video is not None:
        try:
            if probe(video, cfg).get("video"):
                results["review_mp4"] = mux_review(video, mix, out / ("review_final.mp4" if final else "review.mp4"), cfg)
        except Exception as e:
            results["review_error"] = str(e)

    results["markers"] = write_audition(sheet.cues, out / "markers_audition.csv", like=like, sr=sr)
    (out / "script.md").write_text(sheet.script_markdown(), encoding="utf-8")
    (out / "recording_script.md").write_text(recording_script(cfg, sheet), encoding="utf-8")

    if stems:
        bed = ", ".join(k for k in ("music", "effects") if k in stems)
        music_db = float(duck.get("MUSIC", 0.0))
        background_note = (f"Background: stems (dialogue ducked under reads; {bed} "
                           + (f"dipped {music_db:g} dB" if music_db < 0 else "untouched") + ")")
    else:
        background_note = "Background: the film's full mix, ducked under every read"
    L = ["# Build report", "", f"Stem: {cfg.rel(stem)}", f"Mix: {cfg.rel(mix)}", background_note,
         f"Clips placed: {takes_used} recorded takes, {tts_used} synthetic (TTS)",
         f"Peak {stats_mix['peak_db']} dBFS, clipped samples: {stats_mix['clipped_samples']}", ""]
    if missing:
        L += ["## Cues with no audio (no take, TTS off or unavailable)", ""] + [f"- {m}" for m in missing] + [""]
    if collisions:
        L += ["## Overlaps (a line runs into the next one; shorten or re-time)", ""] + [f"- {m}" for m in collisions] + [""]
    (out / "build_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    results["report"] = out / "build_report.md"
    return results
