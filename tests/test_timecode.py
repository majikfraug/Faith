import unittest

from adtool.timecode import fmt_short, fmt_tc, parse_ids, parse_range, parse_tc


class TimecodeTests(unittest.TestCase):
    def test_parse(self):
        self.assertAlmostEqual(parse_tc("83"), 83.0)
        self.assertAlmostEqual(parse_tc("1:23"), 83.0)
        self.assertAlmostEqual(parse_tc("01:23.5"), 83.5)
        self.assertAlmostEqual(parse_tc("1:02:03.456"), 3723.456)
        self.assertAlmostEqual(parse_tc("00:01:23,456"), 83.456)
        self.assertAlmostEqual(parse_tc(12.5), 12.5)
        with self.assertRaises(ValueError):
            parse_tc("abc")

    def test_format(self):
        self.assertEqual(fmt_tc(83.456), "00:01:23.456")
        self.assertEqual(fmt_tc(3723.4), "01:02:03.400")
        self.assertEqual(fmt_short(83.456), "01:23.456")
        self.assertEqual(fmt_short(3723.0), "01:02:03.000")

    def test_range_and_ids(self):
        self.assertEqual(parse_range("0:00-5:00"), (0.0, 300.0))
        self.assertEqual(parse_range("5:00-", 900.0), (300.0, 900.0))
        self.assertEqual(parse_range("all", 900.0), (0.0, 900.0))
        with self.assertRaises(ValueError):
            parse_range("5:00-4:00")
        self.assertEqual(parse_ids("12-14,45, 50"), {12, 13, 14, 45, 50})


if __name__ == "__main__":
    unittest.main()
