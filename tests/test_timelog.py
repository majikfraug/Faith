import copy
import csv
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from adtool import timelog as T
from adtool.config import Config, DEFAULTS

BASE = datetime(2026, 11, 20, 9, 0).astimezone()


def at(minutes):
    return BASE + timedelta(minutes=minutes)


def ev(minutes, kind, text=""):
    return T.Event(at(minutes), kind, text)


def cfg_in(td):
    return Config(Path(td), copy.deepcopy(DEFAULTS))


def totals(res, synthetic=True):
    out = {}
    for m, (_, ph, _) in res.timeline.cells.items():
        part_a = res.split_minute is None or m < res.split_minute
        if part_a == synthetic:
            out[ph] = out.get(ph, 0) + 1
    return out


class ClassifyTests(unittest.TestCase):
    def test_commands_and_words(self):
        self.assertEqual(T.classify("/ad-draft 0:00-5:00"), "draft")
        self.assertEqual(T.classify("/ad-build --final"), "publish")
        self.assertEqual(T.classify("/ad-build"), "build")
        self.assertEqual(T.classify("starting to record now"), "recording")
        self.assertEqual(T.classify("done mixing in Audition"), "mixing")
        self.assertEqual(T.classify("cue 45 is Donna, not a stranger"), None)


class AnalyseTests(unittest.TestCase):
    def run_it(self, events, takes=(), film=70.0):
        with tempfile.TemporaryDirectory() as td:
            return T.analyse(cfg_in(td), events=list(events), takes=list(takes), film_min=film)

    def test_short_gaps_count_and_breaks_do_not(self):
        res = self.run_it([ev(0, "prompt", "/ad-draft 0:00-5:00"), ev(4, "stop"),
                           ev(10, "prompt", "cue 3 is wrong"), ev(12, "stop"),
                           ev(200, "prompt", "make 7 shorter"), ev(201, "stop")])
        t = totals(res)
        self.assertEqual(t.get("draft"), 10)              # 0-10: drafting, then reading the table
        self.assertAlmostEqual(t.get("review"), 4, delta=1)  # 10-12, the 2-minute gap after, 200-201
        self.assertNotIn("other", t)

    def test_claude_reply_counts_even_when_long(self):
        res = self.run_it([ev(0, "prompt", "/ad-draft 0:00-69:00"), ev(50, "stop")])
        self.assertEqual(totals(res).get("draft"), 51)   # the reply, plus the minute it ended (reading it)
        self.assertEqual(len(res.timeline.busy), 50)

    def test_watching_after_build(self):
        res = self.run_it([ev(0, "prompt", "/ad-build"), ev(6, "stop"), ev(85, "prompt", "cue 12 lands on speech")])
        t = totals(res)
        self.assertEqual(t.get("build"), 6)
        self.assertEqual(t.get("watching"), 79)

    def test_recording_files_and_split(self):
        takes = [T.Take(Path("takes/0001.wav"), "recording", at(300), at(302), 120),
                 T.Take(Path("takes/0002.wav"), "recording", at(310), at(311), 60),
                 T.Take(Path("takes/clean/0001.wav"), "cleanup", at(500), at(500), 0)]
        res = self.run_it([ev(0, "prompt", "/ad-setup"), ev(5, "stop")], takes)
        self.assertEqual(totals(res, synthetic=True), {"setup": 6})
        b = totals(res, synthetic=False)
        self.assertEqual(b.get("recording"), 11)
        self.assertEqual(b.get("cleanup"), 1)

    def test_start_and_done_notes(self):
        res = self.run_it([ev(0, "prompt", "starting to record"), ev(1, "stop"),
                           ev(95, "prompt", "done recording, bring the takes in"), ev(97, "stop")])
        self.assertGreaterEqual(totals(res, synthetic=False).get("recording", 0), 95)

    def test_unclosed_start_uses_next_message(self):
        res = self.run_it([ev(0, "prompt", "starting the mix in audition"), ev(1, "stop"),
                           ev(120, "prompt", "/ad-status")])
        self.assertEqual(totals(res, synthetic=False).get("mixing"), 120)
        self.assertTrue(res.flags)

    def test_synthetic_done_note_sets_split(self):
        res = self.run_it([ev(0, "prompt", "/ad-build --final"), ev(10, "stop"),
                           ev(20, "note", "synthetic done"),
                           ev(30, "prompt", "starting to record"), ev(31, "stop"), ev(60, "prompt", "done recording")])
        self.assertEqual(res.split_minute, int(at(20).timestamp() // 60) + 1)
        self.assertIn("recording", totals(res, synthetic=False))
        self.assertNotIn("recording", totals(res, synthetic=True))

    def test_manual_entry_wins(self):
        e = T.Event(at(0), "manual", "studio", "recording", at(120))
        res = self.run_it([e])
        self.assertEqual(totals(res, synthetic=False).get("recording"), 120)


class FileTests(unittest.TestCase):
    def test_hook_writes_rows_and_report_reads_them(self):
        hook = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "timelog.py"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".claude" / "hooks").mkdir(parents=True)
            copy_ = root / ".claude" / "hooks" / "timelog.py"
            copy_.write_text(hook.read_text(encoding="utf-8"), encoding="utf-8")
            for payload in ('{"hook_event_name":"UserPromptSubmit","session_id":"abc123456","prompt":"/ad-setup\\nplease"}',
                            '{"hook_event_name":"Stop","session_id":"abc123456"}', "not json"):
                p = subprocess.run([sys.executable, str(copy_)], input=payload, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0)
                self.assertEqual(p.stdout, "")
            with open(root / "project" / "timelog.csv", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["event"] for r in rows], ["prompt", "stop", "event"])
            self.assertEqual(rows[0]["text"], "/ad-setup please")
            cfg = cfg_in(td)
            T.append(cfg, "manual", "studio", phase="recording", start=at(0), until=at(90))
            res = T.analyse(cfg, film_min=70.0)
            md = T.report(cfg, res)
            self.assertIn("Recording", md)
            self.assertIn("1:30", md)

    def test_read_takes_skips_split_folders(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = cfg_in(td)
            takes = cfg.dir("takes")
            (takes / "session1_split").mkdir()
            (takes / "clean").mkdir()
            for rel in ("0001.wav", "session1_split/0002.wav", "clean/0001.wav", "notes.txt"):
                (takes / rel).write_bytes(b"")
            found = {(t.path.name, t.phase) for t in T.read_takes(cfg)}
            self.assertEqual(found, {("0001.wav", "recording"), ("0001.wav", "cleanup")})


if __name__ == "__main__":
    unittest.main()
