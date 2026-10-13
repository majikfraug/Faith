import tempfile
import unittest
from pathlib import Path

from adtool.subtitles import parse_subtitles

SRT = """1
00:00:01,000 --> 00:00:03,500
<i>Hello</i> there,
friend.

2
00:00:04,000 --> 00:00:06,000
{\\an8}Second line &amp; more

"""

VTT = """WEBVTT
Kind: captions
Language: en

NOTE this is a note

00:01.000 --> 00:03.000 align:start position:0%
Hello <c.colorE5E5E5>world</c>

00:03.000 --> 00:03.010 align:start position:0%
Hello world

00:03.010 --> 00:05.000 align:start position:0%
Hello world again<00:00:04.000><c> and more</c>
"""


class SubtitleTests(unittest.TestCase):
    def _parse(self, text, suffix):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / f"t{suffix}"
            p.write_text(text, encoding="utf-8")
            return parse_subtitles(p)

    def test_srt(self):
        subs = self._parse(SRT, ".srt")
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0].text, "Hello there, friend.")
        self.assertAlmostEqual(subs[0].start, 1.0)
        self.assertAlmostEqual(subs[0].end, 3.5)
        self.assertEqual(subs[1].text, "Second line & more")

    def test_vtt_auto_captions(self):
        subs = self._parse(VTT, ".vtt")
        texts = [s.text for s in subs]
        self.assertEqual(texts, ["Hello world", "again and more"])
        self.assertAlmostEqual(subs[0].end, 3.0)


if __name__ == "__main__":
    unittest.main()
