import copy
import tempfile
import unittest
from pathlib import Path

from adtool.config import Config, DEFAULTS
from adtool.cues import (Cue, CueSheet, build_cues, complement, merge_existing, merge_subtitles, read_csv,
                         union_intervals, write_csv)
from adtool.subtitles import Subtitle


def cfg_in(td):
    return Config(Path(td), copy.deepcopy(DEFAULTS))


class BuilderTests(unittest.TestCase):
    def test_merge_subtitles(self):
        subs = [Subtitle(1, 10, 13, "Hello there,"), Subtitle(2, 13.2, 15, "friend."), Subtitle(3, 15.1, 17, "Yes.")]
        merged = merge_subtitles(subs, 0.3, 7.0)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0][2], "Hello there, friend.")
        self.assertEqual(merged[0][3], [1, 2])

    def test_union_and_complement(self):
        self.assertEqual(union_intervals([(1, 3), (2, 4), (6, 7)]), [(1, 4), (6, 7)])
        self.assertEqual(complement([(1, 4), (6, 7)], 10), [(0, 1), (4, 6), (7, 10)])

    def test_build(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = cfg_in(td)
            subs = [Subtitle(1, 10, 13, "Hello there,"), Subtitle(2, 13.2, 15, "friend.")]
            speech = [(5, 8), (10.1, 14.9), (30, 32)]
            cues = build_cues(cfg, subs, speech, 40)
            self.assertEqual([c.type for c in cues], ["DESC", "DESC", "SUB", "DESC", "DESC"])
            sub = cues[2]
            self.assertEqual(sub.line, "Hello there, friend.")
            self.assertAlmostEqual(sub.start_s, 10.0)
            first = cues[0]
            self.assertAlmostEqual(first.start_s, 0.2)
            self.assertAlmostEqual(first.end_s, 4.7)
            self.assertEqual(first.budget_words(2.5), 11)
            self.assertEqual([c.id for c in cues], [1, 2, 3, 4, 5])

    def test_merge_existing_keeps_edits_and_type_changes(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = cfg_in(td)
            subs = [Subtitle(1, 10, 13, "Hello.")]
            speech = [(5, 8), (10, 13)]
            old = build_cues(cfg, subs, speech, 20)
            old[0].type, old[0].line, old[0].status = "TEXT", "Title: Romulo.", "approved"
            old[2].line = "Hi."  # edited subtitle
            new = build_cues(cfg, subs, speech, 20)
            merged, stats = merge_existing(new, old)
            self.assertEqual(stats["orphaned"], 0)
            self.assertEqual(merged[0].type, "TEXT")
            self.assertEqual(merged[0].line, "Title: Romulo.")
            self.assertEqual(merged[0].id, old[0].id)
            self.assertEqual([c for c in merged if c.type == "SUB"][0].line, "Hi.")


class SheetTests(unittest.TestCase):
    def _sheet(self, td):
        cfg = cfg_in(td)
        cues = [Cue(1, "DESC", 0.2, 4.7, 4.9), Cue(2, "SUB", 10.0, 13.0, 14.9, source_text="Hello.", line="Hello."),
                Cue(3, "DESC", 15.2, 29.7, 29.9)]
        return CueSheet(cfg, cues)

    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            sheet = self._sheet(td)
            sheet.cues[0].line = "Título con acentos, y “comillas”."
            sheet.cues[0].measured_s, sheet.cues[0].measure = 2.5, "tts"
            sheet.cues[0].recompute_fit()
            path = sheet.save()
            back = read_csv(path)
            self.assertEqual(back[0].line, "Título con acentos, y “comillas”.")
            self.assertEqual(back[0].fits, "yes")
            self.assertAlmostEqual(back[2].hard_end_s, 29.9)

    def test_ops(self):
        with tempfile.TemporaryDirectory() as td:
            sheet = self._sheet(td)
            sheet.set(1, line="A man walks.")
            self.assertEqual(sheet.by_id(1).status, "drafted")
            a, b = sheet.split(3, 20.0)
            self.assertLess(a.end_s, 20.0)
            self.assertAlmostEqual(b.start_s, 20.0)
            self.assertEqual(b.id, 4)
            sheet.set(4, line="Night falls.")
            merged = sheet.merge(3, 4)
            self.assertEqual(merged.line, "Night falls.")
            self.assertEqual(len(sheet.cues), 3)
            log = sheet.apply([{"id": 2, "line": "Hi.", "notes": "condensed"},
                               {"new": True, "type": "TEXT", "start": "0:05", "end": "0:08", "line": "Title: Peru."},
                               {"id": 1, "status": "skip"}])
            self.assertEqual(len(log), 3)
            self.assertEqual(sheet.by_id(2).line, "Hi.")
            self.assertEqual(sheet.select(types="TEXT")[0].line, "Title: Peru.")
            self.assertEqual(sheet.by_id(1).status, "skip")
            self.assertEqual(len(sheet.select(rng="0:00-0:10")), 2)

    def test_line_change_sets_recorded_take_aside(self):
        with tempfile.TemporaryDirectory() as td:
            sheet = self._sheet(td)
            c = sheet.by_id(1)
            c.line, c.status, c.clip, c.measured_s, c.measure = "A man walks.", "recorded", "work/takes/0001.wav", 1.2, "take"
            c.recompute_fit()
            sheet.set(1, line="A man walks away.")
            self.assertEqual(c.status, "drafted")
            self.assertEqual(c.clip, "")
            self.assertEqual(c.measure, "")
            self.assertIn("re-record", c.notes)
            sheet.set(1, line="A man walks away.")  # same words again: nothing else changes
            self.assertEqual(c.status, "drafted")

    def test_fit_states(self):
        c = Cue(1, "DESC", 0.0, 3.0, 3.4)
        c.measured_s = 2.9; c.recompute_fit(); self.assertEqual(c.fits, "yes")
        c.measured_s = 3.2; c.recompute_fit(); self.assertEqual(c.fits, "tight")
        c.measured_s = 3.6; c.recompute_fit(); self.assertEqual(c.fits, "no")


if __name__ == "__main__":
    unittest.main()
