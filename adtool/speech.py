"""Speech map: where people are talking in the original soundtrack.

Uses the Silero voice-activity model bundled with faster-whisper (no GPU, no
model download). Optionally transcribes with Whisper for context.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import Config
from .media import convert_audio, probe
from .subtitles import Subtitle


def _newer(dst: Path, src: Path) -> bool:
    return dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime and dst.stat().st_size > 0


def analysis_source(cfg: Config) -> Path:
    m = cfg.media_files()
    src = m["dialogue"] or m["audio"] or m["video"]
    if src is None:
        raise SystemExit("no media found: put the film (and its .srt) in media/ or set paths in ad.config.json")
    return src


def mix_source(cfg: Config) -> Path:
    m = cfg.media_files()
    src = m["audio"] or m["video"]
    if src is None:
        raise SystemExit("no media found: put the film in media/ or set media.video in ad.config.json")
    return src


def ensure_analysis_audio(cfg: Config) -> Path:
    src = analysis_source(cfg)
    dst = cfg.work / "audio" / "analysis_16k.wav"
    if not _newer(dst, src):
        convert_audio(src, dst, 16000, 1, cfg)
    return dst


def ensure_mix_audio(cfg: Config) -> Path:
    src = mix_source(cfg)
    sr = int(cfg.get("audio", "sr", default=48000))
    ch = int(cfg.get("audio", "channels", default=2))
    dst = cfg.work / "audio" / f"mix_{sr}.wav"
    if not _newer(dst, src):
        convert_audio(src, dst, sr, ch, cfg)
    return dst


def ensure_stem_audio(cfg: Config, key: str) -> Path:
    """Convert the dialogue/music/effects stem to the project rate and channel count (cached in work/audio)."""
    src = cfg.media_files()[key]
    if src is None:
        raise SystemExit(f"no {key} stem found: put it in media/ or set media.{key} in ad.config.json")
    sr = int(cfg.get("audio", "sr", default=48000))
    ch = int(cfg.get("audio", "channels", default=2))
    dst = cfg.work / "audio" / f"{key}_{sr}.wav"
    if not _newer(dst, src):
        convert_audio(src, dst, sr, ch, cfg)
    return dst


def merge_segments(segs: List[Tuple[float, float]], gap: float) -> List[Tuple[float, float]]:
    segs = sorted((float(a), float(b)) for a, b in segs if b > a)
    out: List[List[float]] = []
    for a, b in segs:
        if out and a - out[-1][1] < gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _load_16k(path16k: Path):
    """Read the 16 kHz mono analysis WAV as float32 (avoids faster-whisper's PyAV decoder)."""
    import numpy as np
    import soundfile as sf
    data, sr = sf.read(str(path16k), dtype="float32", always_2d=True)
    if sr != 16000:
        raise SystemExit(f"analysis audio is {sr} Hz, expected 16000; delete work/audio and rerun ingest")
    return np.ascontiguousarray(data.mean(axis=1), dtype=np.float32)


def vad_segments(path16k: Path, cfg: Config) -> List[Tuple[float, float]]:
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps  # type: ignore
    except ImportError as e:
        raise SystemExit("faster-whisper is not installed (pip install faster-whisper), "
                         "or run `python ad.py ingest --from-subtitles` to use subtitle timing only") from e
    audio = _load_16k(path16k)
    v = cfg.data.get("vad", {})
    wanted = {
        "threshold": float(v.get("threshold", 0.5)),
        "min_speech_duration_ms": int(v.get("min_speech_ms", 250)),
        "min_silence_duration_ms": int(v.get("min_silence_ms", 300)),
        "speech_pad_ms": int(v.get("pad_ms", 100)),
    }
    fields = {f.name for f in dataclasses.fields(VadOptions)}
    opts = VadOptions(**{k: val for k, val in wanted.items() if k in fields})
    raw = get_speech_timestamps(audio, opts)
    total_s = len(audio) / 16000.0
    segs: List[Tuple[float, float]] = []
    for r in raw:
        a, b = r["start"], r["end"]
        if isinstance(a, (int,)) or a > total_s * 1.5:  # sample indices
            a, b = a / 16000.0, b / 16000.0
        segs.append((float(a), float(b)))
    return merge_segments(segs, float(v.get("merge_gap_s", 0.35)))


def build_speech_map(cfg: Config, duration: float, from_subtitles: bool = False,
                     subs: Optional[List[Subtitle]] = None) -> Dict:
    if from_subtitles:
        if not subs:
            raise SystemExit("--from-subtitles needs a subtitle file")
        segs = merge_segments([(s.start, s.end) for s in subs], float(cfg.get("vad", "merge_gap_s", default=0.35)))
        source = "subtitles"
    else:
        path16k = ensure_analysis_audio(cfg)
        segs = vad_segments(path16k, cfg)
        source = "vad:" + cfg.rel(analysis_source(cfg))
    speech_total = sum(b - a for a, b in segs)
    data = {
        "source": source,
        "duration": duration,
        "params": cfg.data.get("vad", {}),
        "stats": {"segments": len(segs), "speech_s": round(speech_total, 2),
                  "speech_pct": round(100.0 * speech_total / duration, 1) if duration else 0.0},
        "segments": [{"start": round(a, 3), "end": round(b, 3)} for a, b in segs],
    }
    path = cfg.work / "speech.json"
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def load_speech(cfg: Config) -> Dict:
    path = cfg.work / "speech.json"
    if not path.exists():
        raise SystemExit("no speech map yet: run `python ad.py ingest` first")
    return json.loads(path.read_text(encoding="utf-8"))


def transcribe(cfg: Config, model_size: str = "small", language: Optional[str] = None) -> Path:
    """Optional: transcribe the soundtrack with Whisper for extra context (slow on CPU)."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as e:
        raise SystemExit("faster-whisper is not installed") from e
    path16k = ensure_analysis_audio(cfg)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(_load_16k(path16k), language=language, word_timestamps=True, vad_filter=True)
    out = []
    for seg in segments:
        out.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip(),
                    "words": [{"w": w.word, "s": round(w.start, 3), "e": round(w.end, 3)} for w in (seg.words or [])]})
    dst = cfg.work / "transcript.json"
    dst.write_text(json.dumps({"language": info.language, "segments": out}, indent=1, ensure_ascii=False), encoding="utf-8")
    txt = cfg.work / "transcript.txt"
    from .timecode import fmt_short
    txt.write_text("\n".join(f"[{fmt_short(s['start'])} - {fmt_short(s['end'])}] {s['text']}" for s in out), encoding="utf-8")
    return dst
