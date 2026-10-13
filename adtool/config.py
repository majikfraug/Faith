"""Project configuration: ad.config.json at the project root, merged over defaults."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_NAME = "ad.config.json"

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".mxf", ".webm", ".mpg", ".mpeg"}
AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".aac", ".ogg"}
SUB_EXT = {".srt", ".vtt"}

DEFAULTS: Dict[str, Any] = {
    "project_name": "Film",
    "media": {
        # Leave blank to auto-detect the first matching file inside media/.
        "video": "",        # the finished film (video with its soundtrack)
        "audio": "",        # optional: a separate full-mix audio file to use instead of the video's audio
        "dialogue": "",     # optional: a dialogue-only stem; makes the speech map much more accurate
        "subtitles": "",    # .srt or .vtt
    },
    "paths": {"media": "media", "work": "work", "out": "out", "takes": "takes", "project": "project"},
    "ffmpeg": {"ffmpeg": "", "ffprobe": ""},
    "timing": {
        "wps": 2.5,              # words per second the narrator reads at (150 wpm); refined by measuring real takes
        "min_gap_s": 1.2,        # a gap in speech shorter than this is not a description window
        "pad_in_s": 0.2,         # start describing this long after speech stops
        "pad_out_s": 0.3,        # stop describing this long before speech resumes
        "min_window_s": 1.0,     # usable window must be at least this long
        "sub_merge_gap_s": 0.3,  # merge subtitles separated by less than this if the first is unfinished
        "sub_merge_max_s": 7.0,  # ... but only up to this combined length
        "sub_lead_s": 0.3,       # subtitle reads start this long after the original speaker begins
    },
    "vad": {
        "threshold": 0.5,
        "min_speech_ms": 250,
        "min_silence_ms": 300,
        "pad_ms": 100,
        "merge_gap_s": 0.35,
    },
    "tts": {
        "engine": "auto",                 # auto | edge | sapi | say | espeak | none
        "voice": "en-US-AriaNeural",      # edge-tts voice
        "rate": "+0%",                    # edge-tts rate, e.g. "+10%"
        "sapi_voice": "",                 # Windows voice name, blank = default
        "sapi_rate": 0,                   # -10..10
        "say_voice": "Samantha",          # macOS voice
        "say_rate": 175,                  # macOS words per minute
        "espeak_voice": "en-us",
        "espeak_rate": 160,
    },
    "audio": {"sr": 48000, "channels": 2, "voice_rms_db": -20.0, "voice_peak_db": -3.0, "subtype": "PCM_16"},
    "duck": {"SUB": -14.0, "DESC": -7.0, "TEXT": -7.0, "ramp_s": 0.25},
    "frames": {"storyboard_interval_s": 3.0, "thumb_width": 320, "cue_width": 480, "sheet_cols": 4, "sheet_rows": 5, "max_storyboard_frames": 400},
    "takes": {"split_silence_s": 1.0, "split_threshold_db": -40.0, "min_take_s": 0.3},
}


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, root: Path, data: Dict[str, Any]):
        self.root = Path(root)
        self.data = data

    # --- generic access -------------------------------------------------
    def get(self, *keys, default=None):
        node: Any = self.data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def set(self, value, *keys) -> None:
        node = self.data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    # --- paths ----------------------------------------------------------
    def dir(self, key: str) -> Path:
        p = self.root / self.get("paths", key, default=key)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def work(self) -> Path:
        return self.dir("work")

    @property
    def out(self) -> Path:
        return self.dir("out")

    @property
    def project(self) -> Path:
        return self.dir("project")

    @property
    def cues_path(self) -> Path:
        return self.project / "cues.csv"

    def rel(self, path: Path | str) -> str:
        """Path relative to the project root when possible (for CSV and reports)."""
        try:
            return str(Path(path).resolve().relative_to(self.root.resolve())).replace(os.sep, "/")
        except ValueError:
            return str(path)

    def abs(self, path: str | Path) -> Path:
        p = Path(path)
        return p if p.is_absolute() else (self.root / p)

    # --- media detection ------------------------------------------------
    def media_files(self) -> Dict[str, Optional[Path]]:
        media_dir = self.root / self.get("paths", "media", default="media")
        found: Dict[str, Optional[Path]] = {"video": None, "audio": None, "dialogue": None, "subtitles": None}
        for key in found:
            configured = self.get("media", key, default="")
            if configured:
                p = self.abs(configured)
                found[key] = p if p.exists() else None
        if media_dir.exists():
            files = sorted(p for p in media_dir.iterdir() if p.is_file())
            if found["video"] is None:
                vids = [p for p in files if p.suffix.lower() in VIDEO_EXT]
                if not vids:
                    vids = [p for p in files if p.suffix.lower() in AUDIO_EXT and "dialog" not in p.stem.lower()]
                if vids:
                    found["video"] = vids[0]
            if found["subtitles"] is None:
                subs = [p for p in files if p.suffix.lower() in SUB_EXT]
                if subs:
                    found["subtitles"] = subs[0]
            if found["dialogue"] is None:
                dlg = [p for p in files if p.suffix.lower() in AUDIO_EXT and "dialog" in p.stem.lower()]
                if dlg:
                    found["dialogue"] = dlg[0]
        return found

    def save(self) -> Path:
        path = self.root / CONFIG_NAME
        path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


def find_root(start: Optional[Path] = None) -> Path:
    """Walk up from the current directory until ad.config.json or ad.py is found."""
    here = Path(start or os.getcwd()).resolve()
    for p in [here, *here.parents]:
        if (p / CONFIG_NAME).exists() or (p / "ad.py").exists():
            return p
    return here


def load(root: Optional[Path] = None) -> Config:
    root = find_root(root)
    data = copy.deepcopy(DEFAULTS)
    path = root / CONFIG_NAME
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{CONFIG_NAME} is not valid JSON: {e}")
        data = _deep_merge(data, user)
    return Config(root, data)


def write_default(root: Path) -> Path:
    cfg = Config(root, copy.deepcopy(DEFAULTS))
    return cfg.save()
