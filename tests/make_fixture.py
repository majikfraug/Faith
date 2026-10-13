"""Generate a small synthetic film for testing the toolkit end to end.

Needs ffmpeg, espeak-ng, numpy, soundfile, Pillow.  Usage:
    python tests/make_fixture.py <project_dir>
Writes <project_dir>/media/film.mp4 and film.srt (150 s, 640x360, 2 fps).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

SR = 48000
DUR = 150.0
FPS = 2
W, H = 640, 360

# (start, voice, text, subtitle or None)
SPEECH = [
    (5.0, "en-us", "In the mountains of Peru, a young man carried a book that would change his people.", None),
    (20.0, "es-419", "Mañana voy al pueblo para enseñar la palabra de Dios a la gente.", "Tomorrow I will go to the village to teach God's word to the people."),
    (29.0, "es-419", "Ten cuidado, el camino es peligroso.", "Be careful, the road is dangerous."),
    (50.0, "es-419", "Dios nos ha dado su palabra en nuestro idioma, y ahora todos pueden escucharla y entenderla.",
     "God has given us his word in our own language, and now everyone can hear it and understand it."),
    (60.0, "en-us", "The road to Ayacucho wound through valleys where few outsiders traveled.", None),
    (80.0, "es-419", "¿Quién es?", "Who is it?"),
    (82.5, "es-419", "Soy yo, Romulo.", "It's me, Romulo."),
    (100.0, "es-419", "Si vienen esta noche,", "If they come tonight,"),
    (102.7, "es-419", "no vamos a huir.", "we will not run."),
]

SCENES = [  # (start, end, bg colour, big text, small text)
    (0, 5, (10, 10, 40), "ROMULO", "A story from the Andes"),
    (5, 20, (60, 90, 40), "mountain road", "a man walks with a book"),
    (20, 35, (90, 70, 40), "village square", "two men talk by a wall"),
    (35, 50, (90, 70, 40), "village square", "Romulo Saune, Pastor"),
    (50, 66, (40, 60, 90), "inside the church", "people listen"),
    (66, 80, (120, 100, 60), "night, a dirt road", "headlights approach"),
    (80, 100, (30, 30, 30), "doorway at night", "a knock, the door opens"),
    (100, 120, (30, 30, 30), "kitchen table", "the family sits together"),
    (120, 135, (60, 90, 40), "dawn over the valley", ""),
    (135, 150, (0, 0, 0), "Produced by Faith Comes By Hearing", "for the Quechua people"),
]


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def tts(voice: str, text: str, tmp: Path, k: int) -> np.ndarray:
    raw = tmp / f"sp_{k}.wav"
    subprocess.run(["espeak-ng", "-v", voice, "-s", "150", "-w", str(raw), text], check=True, capture_output=True)
    conv = tmp / f"sp_{k}_48k.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-ac", "1", "-ar", str(SR), str(conv)], check=True)
    data, _ = sf.read(str(conv), dtype="float32")
    return data


def music_bed(n: int) -> np.ndarray:
    t = np.arange(n) / SR
    chords = [(220.0, 277.2, 329.6), (196.0, 246.9, 293.7), (174.6, 220.0, 261.6), (196.0, 246.9, 293.7)]
    out = np.zeros(n, dtype=np.float32)
    seg = n // len(chords)
    for i, chord in enumerate(chords):
        sl = slice(i * seg, (i + 1) * seg if i < len(chords) - 1 else n)
        tt = t[sl]
        for f in chord:
            out[sl] += 0.2 * np.sin(2 * np.pi * f * tt) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.1 * tt))
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t)
    return (out * env * 0.12).astype(np.float32)


def main(project: Path) -> None:
    media = project / "media"
    media.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="fixture_"))
    n = int(DUR * SR)
    mix = music_bed(n)
    srt = []
    for k, (start, voice, text, sub) in enumerate(SPEECH):
        clip = tts(voice, text, tmp, k) * 0.8
        i0 = int(start * SR)
        mix[i0:i0 + len(clip)] += clip[: n - i0]
        if sub:
            end = start + len(clip) / SR
            srt.append((start, end, sub))
    stereo = np.stack([mix, mix], axis=1)
    audio = tmp / "audio.wav"
    sf.write(str(audio), np.clip(stereo, -1, 1), SR, subtype="PCM_16")

    def tc(t):
        h, r = divmod(int(t * 1000), 3600000)
        m, r = divmod(r, 60000)
        s, ms = divmod(r, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for k, (a, b, text) in enumerate(srt, 1):
        lines += [str(k), f"{tc(a)} --> {tc(b)}", text, ""]
    (media / "film.srt").write_text("\n".join(lines), encoding="utf-8")

    frames = tmp / "frames"
    frames.mkdir()
    big, small, clock = font(44), font(26), font(20)
    total = int(DUR * FPS)
    for i in range(total):
        t = i / FPS
        scene = next(s for s in SCENES if s[0] <= t < s[1])
        im = Image.new("RGB", (W, H), scene[2])
        d = ImageDraw.Draw(im)
        d.text((30, 120), scene[3], fill=(240, 240, 240), font=big)
        if scene[4]:
            d.text((30, 190), scene[4], fill=(220, 220, 180), font=small)
        d.text((W - 150, H - 40), f"{int(t // 60):02d}:{t % 60:04.1f}", fill=(255, 255, 0), font=clock)
        sub = next((s for s in srt if s[0] <= t < s[1]), None)
        if sub:
            d.rectangle([0, H - 80, W, H - 50], fill=(0, 0, 0))
            d.text((20, H - 78), sub[2], fill=(255, 255, 255), font=small)
        im.save(frames / f"f_{i:05d}.png")
    out = media / "film.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", str(frames / "f_%05d.png"),
                    "-i", str(audio), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {out} and {media / 'film.srt'} ({len(srt)} subtitles)")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "fixture_project"))
