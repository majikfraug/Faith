"""End-to-end smoke test on a synthetic film. Needs ffmpeg and espeak-ng.

    python tests/smoke.py            # builds a fixture in a temp folder and runs the whole pipeline
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
AD = str(ROOT / "ad.py")


def run(args, cwd):
    print("$", " ".join(args[1:]) if args[0] == PY else " ".join(args))
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(proc.stdout.strip())
    if proc.returncode != 0:
        print(proc.stderr)
        raise SystemExit(f"step failed: {' '.join(args)}")
    return proc.stdout


def main() -> int:
    if not shutil.which("ffmpeg") or not shutil.which("espeak-ng"):
        print("smoke test needs ffmpeg and espeak-ng on PATH; skipping")
        return 0
    td = Path(tempfile.mkdtemp(prefix="ad_smoke_"))
    try:
        run([PY, str(ROOT / "tests" / "make_fixture.py"), str(td)], td)
        run([PY, AD, "init"], td)
        run([PY, AD, "doctor"], td)
        run([PY, AD, "ingest"], td)
        run([PY, AD, "cues", "build"], td)
        out = run([PY, AD, "cues", "show", "--type", "DESC"], td)
        desc_ids = [int(line.split()[0]) for line in out.splitlines() if line.strip() and line.split()[0].isdigit()]
        assert len(desc_ids) >= 6, desc_ids
        run([PY, AD, "frames", "--range", "0:00-2:30"], td)
        packet = td / "work" / "packets" / "packet_0000-0230.md"
        assert packet.exists() and "Storyboard sheets" in packet.read_text(encoding="utf-8")
        drafts = [{"id": i, "line": f"Description number {i} for this window.", "status": "drafted"} for i in desc_ids]
        drafts.append({"new": True, "type": "TEXT", "start": "0:40", "end": "0:44", "line": "Caption: Romulo Saune, Pastor."})
        dpath = td / "project" / "drafts" / "drafts_test.json"
        dpath.parent.mkdir(parents=True, exist_ok=True)
        dpath.write_text(json.dumps(drafts), encoding="utf-8")
        run([PY, AD, "cues", "apply", str(dpath)], td)
        run([PY, AD, "fit", "--engine", "espeak"], td)
        run([PY, AD, "build", "--engine", "espeak"], td)
        for name in ("stem.wav", "mix_review.wav", "review.mp4", "markers_audition.csv", "script.md", "recording_script.md"):
            assert (td / "out" / name).exists(), name
        run([PY, str(ROOT / "tests" / "make_takes.py"), str(td)], td)
        run([PY, AD, "takes", "--file", str(td / "takes" / "session1.wav")], td)
        run([PY, AD, "build", "--final", "--no-tts"], td)
        assert (td / "out" / "final" / "youtube_descriptive_audio.wav").exists()
        run([PY, AD, "cues", "build"], td)  # rebuild must keep everything
        status = run([PY, AD, "status"], td)
        assert "recorded" in status
        print("\nSMOKE TEST PASSED")
        return 0
    finally:
        shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
