"""ffmpeg / ffprobe helpers."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import Config


class MediaError(RuntimeError):
    pass


_FF_CACHE: Optional[Tuple[str, str]] = None


def find_ffmpeg(cfg: Optional[Config] = None) -> Tuple[str, str]:
    """Return (ffmpeg, ffprobe) executables. Order: config, PATH, static-ffmpeg package."""
    global _FF_CACHE
    if _FF_CACHE:
        return _FF_CACHE
    candidates: List[Tuple[str, str]] = []
    if cfg is not None:
        a = cfg.get("ffmpeg", "ffmpeg", default="") or ""
        b = cfg.get("ffmpeg", "ffprobe", default="") or ""
        if a and b:
            candidates.append((a, b))
    w1, w2 = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if w1 and w2:
        candidates.append((w1, w2))
    for ff, fp in candidates:
        if (shutil.which(ff) or Path(ff).exists()) and (shutil.which(fp) or Path(fp).exists()):
            _FF_CACHE = (ff, fp)
            return _FF_CACHE
    try:  # pip install static-ffmpeg  (downloads binaries on first use)
        from static_ffmpeg import run as _sf_run  # type: ignore
        ff, fp = _sf_run.get_or_fetch_platform_executables_else_raise()
        _FF_CACHE = (str(ff), str(fp))
        return _FF_CACHE
    except Exception:
        pass
    raise MediaError(
        "ffmpeg was not found. Install it (Windows: `winget install Gyan.FFmpeg`, Mac: `brew install ffmpeg`), "
        "or run `pip install static-ffmpeg` inside the project's .venv, or set ffmpeg paths in ad.config.json."
    )


def run(cmd: List[str], quiet: bool = True) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError as e:
        raise MediaError(f"could not run {cmd[0]}: {e}")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        raise MediaError(f"command failed ({proc.returncode}): {' '.join(cmd[:6])} ...\n" + "\n".join(tail))
    return proc


def probe(path: Path, cfg: Optional[Config] = None) -> Dict:
    _, ffprobe = find_ffmpeg(cfg)
    proc = run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    info = json.loads(proc.stdout or "{}")
    fmt = info.get("format", {})
    out: Dict = {"path": str(path), "duration": float(fmt.get("duration") or 0.0), "video": None, "audio": None}
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and out["video"] is None and s.get("disposition", {}).get("attached_pic", 0) == 0:
            fr = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1"
            try:
                num, den = fr.split("/")
                fps = float(num) / float(den) if float(den) else 0.0
            except Exception:
                fps = 0.0
            out["video"] = {"codec": s.get("codec_name"), "width": s.get("width"), "height": s.get("height"), "fps": round(fps, 3)}
        elif s.get("codec_type") == "audio" and out["audio"] is None:
            out["audio"] = {"codec": s.get("codec_name"), "sample_rate": int(s.get("sample_rate") or 0), "channels": int(s.get("channels") or 0)}
            if not out["duration"] and s.get("duration"):
                out["duration"] = float(s["duration"])
    return out


def convert_audio(src: Path, dst: Path, sr: int, channels: int, cfg: Optional[Config] = None,
                  start: Optional[float] = None, duration: Optional[float] = None) -> Path:
    """Decode any media file to PCM 16-bit WAV at the given rate/channels."""
    ffmpeg, _ = find_ffmpeg(cfg)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-v", "error", "-nostdin"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(src), "-vn", "-ac", str(channels), "-ar", str(sr), "-c:a", "pcm_s16le", str(dst)]
    run(cmd)
    return dst


def extract_frame(src: Path, t: float, dst: Path, width: int, cfg: Optional[Config] = None) -> Path:
    """Grab the frame at time t. Near the very end of a file ffmpeg can return nothing, so step back a little."""
    ffmpeg, _ = find_ffmpeg(cfg)
    dst.parent.mkdir(parents=True, exist_ok=True)
    for back in (0.0, 0.5, 1.0, 2.0, 4.0):
        if dst.exists():
            dst.unlink()
        run([ffmpeg, "-y", "-v", "error", "-nostdin", "-ss", f"{max(0.0, t - back):.3f}", "-i", str(src),
             "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(dst)])
        if dst.exists() and dst.stat().st_size > 0:
            return dst
    raise MediaError(f"could not extract a frame at {t:.2f}s from {src.name}")


def extract_frames_interval(src: Path, start: float, end: float, interval: float, width: int,
                            out_dir: Path, prefix: str, cfg: Optional[Config] = None) -> List[Tuple[float, Path]]:
    """Grab one frame every `interval` seconds between start and end with a single ffmpeg call."""
    ffmpeg, _ = find_ffmpeg(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{prefix}_*.jpg"):
        old.unlink()
    pattern = out_dir / f"{prefix}_%05d.jpg"
    run([ffmpeg, "-y", "-v", "error", "-nostdin", "-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.0, end - start):.3f}",
         "-i", str(src), "-vf", f"fps=1/{interval},scale={width}:-2", "-q:v", "4", str(pattern)])
    frames = sorted(out_dir.glob(f"{prefix}_*.jpg"))
    return [(start + k * interval, p) for k, p in enumerate(frames)]


def mux_review(video: Path, audio: Path, dst: Path, cfg: Optional[Config] = None) -> Path:
    """Copy the video stream and replace its audio with the review mix."""
    ffmpeg, _ = find_ffmpeg(cfg)
    dst.parent.mkdir(parents=True, exist_ok=True)
    run([ffmpeg, "-y", "-v", "error", "-nostdin", "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(dst)])
    return dst


def encode_aac(src: Path, dst: Path, cfg: Optional[Config] = None, bitrate: str = "256k") -> Path:
    ffmpeg, _ = find_ffmpeg(cfg)
    run([ffmpeg, "-y", "-v", "error", "-nostdin", "-i", str(src), "-c:a", "aac", "-b:a", bitrate, str(dst)])
    return dst
