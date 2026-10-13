"""Text-to-speech for fit checking and draft tracks.

Engines, tried in this order when engine = "auto":
  edge   - edge-tts (free Microsoft neural voices; needs internet)
  sapi   - Windows built-in voices via PowerShell (offline)
  say    - macOS built-in voices (offline)
  espeak - espeak-ng if installed (offline, robotic but fine for timing)
Clips are cached in work/tts/ by text+voice, trimmed of silence, and normalized.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from . import audio as A
from .config import Config
from .media import MediaError, convert_audio

ENGINE_ORDER = ("edge", "sapi", "say", "espeak")
SAMPLE_TEXT = "A man in a blue shirt walks along a dirt road toward a village in the mountains."


class TTSError(RuntimeError):
    pass


_failed: set = set()


def engine_available(name: str) -> Tuple[bool, str]:
    sysname = platform.system()
    if name == "edge":
        ok = importlib.util.find_spec("edge_tts") is not None
        return ok, "edge-tts installed (needs internet)" if ok else "pip install edge-tts"
    if name == "sapi":
        ok = sysname == "Windows" and (shutil.which("powershell") is not None or shutil.which("pwsh") is not None)
        return ok, "Windows voices via PowerShell" if ok else "Windows only"
    if name == "say":
        ok = sysname == "Darwin" and shutil.which("say") is not None
        return ok, "macOS say" if ok else "macOS only"
    if name == "espeak":
        ok = shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None
        return ok, "espeak-ng found" if ok else "espeak-ng not installed"
    return False, "unknown engine"


def available_engines() -> List[str]:
    return [e for e in ENGINE_ORDER if engine_available(e)[0]]


def pick_engine(cfg: Config, requested: Optional[str] = None) -> str:
    want = (requested or cfg.get("tts", "engine", default="auto") or "auto").lower()
    if want == "none":
        return "none"
    if want != "auto":
        ok, why = engine_available(want)
        if not ok:
            raise TTSError(f"TTS engine '{want}' is not available: {why}")
        return want
    for e in ENGINE_ORDER:
        if e in _failed:
            continue
        if engine_available(e)[0]:
            return e
    return "none"


def _voice_tag(cfg: Config, engine: str) -> str:
    t = cfg.data.get("tts", {})
    if engine == "edge":
        return f"{t.get('voice')}|{t.get('rate')}"
    if engine == "sapi":
        return f"{t.get('sapi_voice')}|{t.get('sapi_rate')}"
    if engine == "say":
        return f"{t.get('say_voice')}|{t.get('say_rate')}"
    if engine == "espeak":
        return f"{t.get('espeak_voice')}|{t.get('espeak_rate')}"
    return ""


def cache_path(cfg: Config, engine: str, text: str) -> Path:
    key = hashlib.sha1(f"{engine}|{_voice_tag(cfg, engine)}|{text.strip()}".encode("utf-8")).hexdigest()[:20]
    d = cfg.work / "tts"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.wav"


def _run(cmd: List[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
        raise TTSError(f"{cmd[0]} failed: " + " | ".join(tail))


def _edge(cfg: Config, text: str, raw: Path) -> None:
    import edge_tts  # type: ignore

    voice = cfg.get("tts", "voice", default="en-US-AriaNeural")
    rate = cfg.get("tts", "rate", default="+0%")
    proxy = os.environ.get("AD_TTS_PROXY") or None

    async def go():
        kwargs = {"rate": rate}
        if proxy:
            kwargs["proxy"] = proxy
        comm = edge_tts.Communicate(text, voice, **kwargs)
        await comm.save(str(raw))

    try:
        asyncio.run(go())
    except Exception as e:  # network, voice name, service hiccup
        raise TTSError(f"edge-tts failed ({type(e).__name__}: {e})")
    if not raw.exists() or raw.stat().st_size == 0:
        raise TTSError("edge-tts produced no audio")


def _sapi(cfg: Config, text: str, raw: Path, txt: Path) -> None:
    voice = cfg.get("tts", "sapi_voice", default="") or ""
    rate = int(cfg.get("tts", "sapi_rate", default=0) or 0)
    script = txt.with_suffix(".ps1")
    select = f'$s.SelectVoice("{voice}")' if voice else ""
    script.write_text(
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        f"{select}\n"
        f"$s.Rate = {rate}\n"
        f'$s.SetOutputToWaveFile("{raw}")\n'
        f'$t = [IO.File]::ReadAllText("{txt}")\n'
        "$s.Speak($t)\n"
        "$s.Dispose()\n",
        encoding="utf-8",
    )
    ps = shutil.which("powershell") or shutil.which("pwsh")
    _run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)])


def _say(cfg: Config, text: str, raw: Path, txt: Path) -> None:
    voice = cfg.get("tts", "say_voice", default="Samantha")
    rate = int(cfg.get("tts", "say_rate", default=175))
    _run(["say", "-v", voice, "-r", str(rate), "-o", str(raw), "-f", str(txt)])


def _espeak(cfg: Config, text: str, raw: Path, txt: Path) -> None:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    voice = cfg.get("tts", "espeak_voice", default="en-us")
    rate = int(cfg.get("tts", "espeak_rate", default=160))
    _run([exe, "-v", voice, "-s", str(rate), "-w", str(raw), "-f", str(txt)])


def synth(cfg: Config, text: str, engine: Optional[str] = None) -> Tuple[Path, str]:
    """Synthesize text to a trimmed, normalized mono WAV at the project sample rate. Returns (path, engine)."""
    text = " ".join(text.split())
    if not text:
        raise TTSError("nothing to say")
    chosen = pick_engine(cfg, engine)
    if chosen == "none":
        raise TTSError("no TTS engine available (install edge-tts, or use Windows/macOS built-in voices)")
    auto = (engine or cfg.get("tts", "engine", default="auto")) == "auto"
    sr = int(cfg.get("audio", "sr", default=48000))
    while True:
        dst = cache_path(cfg, chosen, text)
        if dst.exists():
            return dst, chosen
        try:
            with tempfile.TemporaryDirectory() as td:
                tdp = Path(td)
                txt = tdp / "line.txt"
                txt.write_text(text, encoding="utf-8")
                if chosen == "edge":
                    raw = tdp / "raw.mp3"
                    _edge(cfg, text, raw)
                elif chosen == "sapi":
                    raw = tdp / "raw.wav"
                    _sapi(cfg, text, raw, txt)
                elif chosen == "say":
                    raw = tdp / "raw.aiff"
                    _say(cfg, text, raw, txt)
                elif chosen == "espeak":
                    raw = tdp / "raw.wav"
                    _espeak(cfg, text, raw, txt)
                else:
                    raise TTSError(f"unknown engine {chosen}")
                wav = tdp / "conv.wav"
                convert_audio(raw, wav, sr, 1, cfg)
                data, _ = A.read(wav)
            mono = A.trim_silence(A.to_mono(data), sr)
            mono = A.normalize_voice(mono, float(cfg.get("audio", "voice_rms_db", default=-20.0)),
                                     float(cfg.get("audio", "voice_peak_db", default=-3.0)))
            A.write(dst, mono, sr)
            return dst, chosen
        except (TTSError, MediaError) as e:
            if not auto:
                raise
            _failed.add(chosen)
            nxt = pick_engine(cfg, "auto")
            if nxt == "none":
                raise TTSError(f"{chosen} failed ({e}) and no other engine is available")
            print(f"  note: {chosen} failed ({e}); falling back to {nxt}")
            chosen = nxt


def measure(path: Path) -> float:
    return A.duration(path)


def test_voice(cfg: Config, engine: Optional[str] = None) -> Tuple[Path, str, float]:
    path, used = synth(cfg, SAMPLE_TEXT, engine)
    return path, used, measure(path)
