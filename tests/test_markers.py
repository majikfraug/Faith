import tempfile
import unittest
from pathlib import Path

from adtool.cues import Cue
from adtool.markers import write_audition


class MarkerTests(unittest.TestCase):
    def test_default_and_template(self):
        cues = [Cue(1, "DESC", 0.2, 4.7, 4.9, line="A man walks."), Cue(2, "SUB", 3725.0, 3728.0, 3729.0, line="Hello"),
                Cue(3, "DESC", 9.0, 10.0, 10.0, line="skipped", status="skip")]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            out = write_audition(cues, td / "m.csv")
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], "Name\tStart\tDuration\tTime Format\tType\tDescription")
            self.assertEqual(lines[1], "0001 DESC\t0:00.200\t0:04.500\tdecimal\tCue\tA man walks.")
            self.assertEqual(lines[2].split("\t")[1], "62:05.000")
            self.assertEqual(len(lines), 3)
            tpl = td / "export.csv"
            tpl.write_text("Name,Start,Duration,Time Format,Type,Description\nMarker 01,0:00:01.500,0:00:00.000,decimal,Cue,\n")
            out = write_audition(cues, td / "m2.csv", like=tpl)
            lines = out.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[1], "0001 DESC,0:00:00.200,0:00:04.500,decimal,Cue,A man walks.")
            self.assertEqual(lines[2].split(",")[1], "1:02:05.000")


if __name__ == "__main__":
    unittest.main()
