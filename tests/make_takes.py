"""Fake a narrator's one-pass recording for testing: reads every non-skipped line from the cue
sheet with espeak-ng (a different voice than the fixture film) separated by 1.6 s pauses.

Usage: python tests/make_takes.py <project_dir> [out.wav]
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adtool.cues import read_csv  # noqa: E402

SR = 48000


def main(project: Path, out: Path) -> None:
    cues = [c for c in read_csv(project / "project" / "cues.csv") if c.status != "skip" and c.line.strip()]
    tmp = Path(tempfile.mkdtemp(prefix="takes_"))
    pieces = [np.zeros(int(1.0 * SR), dtype=np.float32)]
    for c in cues:
        raw = tmp / f"{c.id}.wav"
        subprocess.run(["espeak-ng", "-v", "en-gb", "-s", "150", "-w", str(raw), c.line], check=True, capture_output=True)
        conv = tmp / f"{c.id}_48k.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-ac", "1", "-ar", str(SR), str(conv)], check=True)
        data, _ = sf.read(str(conv), dtype="float32")
        pieces.append(data * 0.7)
        pieces.append(np.zeros(int(1.6 * SR), dtype=np.float32))
    audio = np.concatenate(pieces)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), audio, SR, subtype="PCM_16")
    print(f"wrote {out}: {len(cues)} lines, {len(audio) / SR:.1f}s")


if __name__ == "__main__":
    proj = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else proj / "takes" / "session1.wav"
    main(proj, dst)
