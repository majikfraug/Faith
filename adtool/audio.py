"""WAV handling with numpy + soundfile: trimming, splitting, placing clips, ducking, mixing.

Everything here works in float32 and processes long files in blocks, so a
67-minute film never has to fit in memory at once.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf


class AudioError(RuntimeError):
    pass


def info(path: Path) -> Tuple[int, int, int]:
    i = sf.info(str(path))
    return i.frames, i.samplerate, i.channels


def duration(path: Path) -> float:
    frames, sr, _ = info(path)
    return frames / float(sr)


def read(path: Path) -> Tuple[np.ndarray, int]:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return data, int(sr)


def write(path: Path, data: np.ndarray, sr: int, subtype: str = "PCM_16") -> Path:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if data.ndim == 1:
        data = data[:, None]
    sf.write(str(path), np.clip(data, -1.0, 1.0), sr, subtype=subtype)
    return Path(path)


def to_mono(data: np.ndarray) -> np.ndarray:
    if data.ndim == 1:
        return data.astype(np.float32)
    return data.mean(axis=1).astype(np.float32)


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def gain_to_db(g: float) -> float:
    return 20.0 * math.log10(max(g, 1e-9))


def frame_rms_db(mono: np.ndarray, sr: int, frame_ms: float = 10.0) -> Tuple[np.ndarray, int]:
    """RMS level in dBFS for consecutive frames of frame_ms. Returns (levels, hop_samples)."""
    hop = max(1, int(sr * frame_ms / 1000.0))
    n = len(mono)
    if n == 0:
        return np.full(0, -100.0, dtype=np.float32), hop
    nframes = int(math.ceil(n / hop))
    padded = np.zeros(nframes * hop, dtype=np.float32)
    padded[:n] = mono
    frames = padded.reshape(nframes, hop)
    rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    return (20.0 * np.log10(rms + 1e-9)).astype(np.float32), hop


def trim_silence(mono: np.ndarray, sr: int, threshold_db: float = -45.0, pad_s: float = 0.05) -> np.ndarray:
    levels, hop = frame_rms_db(mono, sr)
    loud = np.where(levels > threshold_db)[0]
    if len(loud) == 0:
        return mono
    pad = int(pad_s * sr)
    start = max(0, loud[0] * hop - pad)
    end = min(len(mono), (loud[-1] + 1) * hop + pad)
    return mono[start:end]


def normalize_voice(mono: np.ndarray, rms_target_db: float = -20.0, peak_target_db: float = -3.0) -> np.ndarray:
    """Bring a voice clip to a consistent loudness without letting peaks exceed the ceiling."""
    if len(mono) == 0:
        return mono
    levels, _ = frame_rms_db(mono, sr=48000)  # frame size only affects the estimate slightly
    voiced = levels[levels > -50.0]
    if len(voiced) == 0:
        return mono
    current_rms_db = float(np.mean(voiced))
    peak = float(np.max(np.abs(mono)) + 1e-9)
    g_rms = db_to_gain(rms_target_db - current_rms_db)
    g_peak = db_to_gain(peak_target_db) / peak
    return (mono * min(g_rms, g_peak)).astype(np.float32)


def split_on_silence(mono: np.ndarray, sr: int, min_silence_s: float = 1.0, threshold_db: float = -40.0,
                     min_segment_s: float = 0.3, pad_s: float = 0.08) -> List[Tuple[float, float]]:
    """Find spoken segments separated by at least min_silence_s of quiet. Returns seconds."""
    levels, hop = frame_rms_db(mono, sr)
    loud = levels > threshold_db
    runs: List[List[int]] = []
    i = 0
    n = len(loud)
    while i < n:
        if loud[i]:
            j = i
            while j < n and loud[j]:
                j += 1
            runs.append([i, j])
            i = j
        else:
            i += 1
    if not runs:
        return []
    min_gap_frames = int(min_silence_s * sr / hop)
    merged: List[List[int]] = [runs[0]]
    for r in runs[1:]:
        if r[0] - merged[-1][1] < min_gap_frames:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    out: List[Tuple[float, float]] = []
    total_s = len(mono) / sr
    for s, e in merged:
        s_t = max(0.0, s * hop / sr - pad_s)
        e_t = min(total_s, e * hop / sr + pad_s)
        if e_t - s_t >= min_segment_s:
            out.append((s_t, e_t))
    return out


def build_gain_grid(total_s: float, spans: Sequence[Tuple[float, float, float]], ramp_s: float,
                    step_s: float = 0.005) -> Tuple[np.ndarray, np.ndarray]:
    """Piecewise-linear ducking envelope sampled every step_s. spans = (start, end, depth_db)."""
    grid_t = np.arange(0.0, total_s + step_s, step_s, dtype=np.float64)
    grid_g = np.ones_like(grid_t)
    ramp = max(ramp_s, step_s)
    for t0, t1, depth_db in spans:
        g = db_to_gain(depth_db)
        a = max(0.0, t0 - ramp)
        b = min(total_s, t1 + ramp)
        i0, i1 = int(a / step_s), int(b / step_s) + 1
        seg_t = grid_t[i0:i1]
        env = np.interp(seg_t, [a, t0, t1, b], [1.0, g, g, 1.0])
        grid_g[i0:i1] = np.minimum(grid_g[i0:i1], env)
    return grid_t, grid_g


def render(total_s: float, sr: int, channels: int, placements: Sequence[Dict], out_path: Path,
           background: Optional[Path] = None, duck_spans: Optional[Sequence[Tuple[float, float, float]]] = None,
           ramp_s: float = 0.25, subtype: str = "PCM_16", block_s: float = 10.0,
           backgrounds: Optional[Sequence[Dict]] = None) -> Dict:
    """Write a timeline: background layers (each ducked on its own) plus clips placed at their start times.

    placements: dicts with keys start (s), path (wav at project sr), gain (linear, default 1.0).
    backgrounds: dicts with keys path (wav at project sr), duck_spans (optional list of (start, end, depth_db)),
    gain (linear, default 1.0). `background` + `duck_spans` is the one-layer shorthand.
    """
    total_frames = int(round(total_s * sr))
    clips = []
    for p in placements:
        data, csr = read(Path(p["path"]))
        if csr != sr:
            raise AudioError(f"{p['path']} is {csr} Hz but the project runs at {sr} Hz; convert it first")
        mono = to_mono(data) * float(p.get("gain", 1.0))
        start = int(round(float(p["start"]) * sr))
        clips.append((start, start + len(mono), mono))
    clips.sort(key=lambda c: c[0])

    layer_specs = list(backgrounds or [])
    if background is not None:
        layer_specs.insert(0, {"path": background, "duck_spans": duck_spans})
    layers = []  # (file, channels, gain grid or None, gain)
    for spec in layer_specs:
        f = sf.SoundFile(str(spec["path"]), "r")
        if f.samplerate != sr:
            for g in layers:
                g[0].close()
            f.close()
            raise AudioError(f"{spec['path']} is {f.samplerate} Hz, expected {sr} Hz")
        spans = spec.get("duck_spans")
        grid = build_gain_grid(total_s, spans, ramp_s) if spans else None
        layers.append((f, f.channels, grid, float(spec.get("gain", 1.0))))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    block_len = int(block_s * sr)
    clipped = 0
    peak = 0.0
    with sf.SoundFile(str(out_path), "w", samplerate=sr, channels=channels, subtype=subtype) as out:
        pos = 0
        while pos < total_frames:
            n = min(block_len, total_frames - pos)
            block = np.zeros((n, channels), dtype=np.float32)
            for f, f_channels, grid, gain in layers:
                chunk = f.read(n, dtype="float32", always_2d=True)
                if len(chunk) < n:
                    chunk = np.vstack([chunk, np.zeros((n - len(chunk), f_channels), dtype=np.float32)])
                if f_channels == channels:
                    layer = chunk
                elif f_channels == 1:
                    layer = np.repeat(chunk, channels, axis=1)
                else:
                    layer = np.repeat(chunk.mean(axis=1, keepdims=True), channels, axis=1)
                if gain != 1.0:
                    layer = layer * gain
                if grid is not None:
                    times = (pos + np.arange(n, dtype=np.float64)) / sr
                    g = np.interp(times, grid[0], grid[1]).astype(np.float32)
                    layer = layer * g[:, None]
                block += layer
            for c_start, c_end, mono in clips:
                if c_end <= pos:
                    continue
                if c_start >= pos + n:
                    break
                lo = max(c_start, pos)
                hi = min(c_end, pos + n)
                seg = mono[lo - c_start:hi - c_start]
                block[lo - pos:hi - pos, :] += seg[:, None]
            absmax = float(np.max(np.abs(block))) if n else 0.0
            peak = max(peak, absmax)
            if absmax > 1.0:
                clipped += int(np.sum(np.abs(block) > 1.0))
                np.clip(block, -1.0, 1.0, out=block)
            out.write(block)
            pos += n
    for f, _, _, _ in layers:
        f.close()
    return {"frames": total_frames, "clipped_samples": clipped, "peak_db": round(gain_to_db(peak), 2) if peak > 0 else -100.0}
