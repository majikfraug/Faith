import tempfile
import unittest
from pathlib import Path

import numpy as np

from adtool import audio as A


def tone(sr, seconds, amp=0.3, f=440.0):
    t = np.arange(int(sr * seconds)) / sr
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


class AudioTests(unittest.TestCase):
    sr = 48000

    def test_trim_and_split(self):
        sr = self.sr
        quiet = np.zeros(int(1.5 * sr), dtype=np.float32)
        sig = np.concatenate([quiet, tone(sr, 1.0), quiet, tone(sr, 0.5), quiet])
        trimmed = A.trim_silence(sig, sr)
        self.assertAlmostEqual(len(trimmed) / sr, 3.1, delta=0.1)
        segs = A.split_on_silence(sig, sr, min_silence_s=1.0, threshold_db=-40.0)
        self.assertEqual(len(segs), 2)
        self.assertAlmostEqual(segs[0][0], 1.5, delta=0.1)
        self.assertAlmostEqual(segs[1][1] - segs[1][0], 0.5, delta=0.2)

    def test_gain_grid(self):
        t, g = A.build_gain_grid(10.0, [(4.0, 6.0, -20.0)], ramp_s=0.5)
        at = lambda x: float(np.interp(x, t, g))
        self.assertAlmostEqual(at(1.0), 1.0)
        self.assertAlmostEqual(at(5.0), 0.1, places=3)
        self.assertAlmostEqual(at(3.75), 0.55, places=2)
        self.assertAlmostEqual(at(7.0), 1.0)

    def test_render_places_and_ducks(self):
        sr = self.sr
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            bg = td / "bg.wav"
            A.write(bg, np.stack([tone(sr, 10.0, 0.5)] * 2, axis=1), sr)
            clip = td / "clip.wav"
            A.write(clip, tone(sr, 1.0, 0.2, 880.0), sr)
            out = td / "mix.wav"
            stats = A.render(10.0, sr, 2, [{"start": 4.0, "path": clip}], out, background=bg,
                             duck_spans=[(4.0, 5.0, -20.0)], ramp_s=0.1)
            data, _ = A.read(out)
            self.assertEqual(len(data), 10 * sr)
            self.assertEqual(stats["clipped_samples"], 0)
            before = np.sqrt(np.mean(data[int(2 * sr):int(3 * sr), 0] ** 2))
            during = np.sqrt(np.mean(data[int(4.2 * sr):int(4.8 * sr), 0] ** 2))
            self.assertAlmostEqual(before, 0.5 / np.sqrt(2), delta=0.01)
            # background at 0.05 amplitude plus the 0.2 clip (uncorrelated tones): rms ≈ sqrt(0.05²/2 + 0.2²/2)
            self.assertAlmostEqual(during, np.sqrt(0.05 ** 2 / 2 + 0.2 ** 2 / 2), delta=0.01)


    def test_render_stems_duck_independently(self):
        sr = self.sr
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            dialogue = td / "dialogue.wav"
            A.write(dialogue, np.stack([tone(sr, 10.0, 0.5)] * 2, axis=1), sr)
            music = td / "music.wav"
            A.write(music, tone(sr, 10.0, 0.3, 660.0), sr)  # mono: must be spread to both channels
            clip = td / "clip.wav"
            A.write(clip, tone(sr, 1.0, 0.2, 880.0), sr)
            out = td / "mix.wav"
            stats = A.render(10.0, sr, 2, [{"start": 4.0, "path": clip}], out, ramp_s=0.1,
                             backgrounds=[{"path": dialogue, "duck_spans": [(4.0, 5.0, -20.0)]},
                                          {"path": music}])
            data, _ = A.read(out)
            self.assertEqual(stats["clipped_samples"], 0)
            rms = lambda a, b, c=0: np.sqrt(np.mean(data[int(a * sr):int(b * sr), c] ** 2))
            # uncorrelated tones add in power
            self.assertAlmostEqual(rms(2.0, 3.0), np.sqrt((0.5 ** 2 + 0.3 ** 2) / 2), delta=0.01)
            self.assertAlmostEqual(rms(2.0, 3.0, 1), rms(2.0, 3.0, 0), delta=0.001)
            # during the clip only the dialogue layer is ducked (0.5 -> 0.05); music stays at 0.3
            self.assertAlmostEqual(rms(4.2, 4.8), np.sqrt((0.05 ** 2 + 0.3 ** 2 + 0.2 ** 2) / 2), delta=0.01)


if __name__ == "__main__":
    unittest.main()
