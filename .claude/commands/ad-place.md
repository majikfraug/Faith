---
description: Guide a recording session and import the narrator's takes into the cue sheet
argument-hint: [range like 0:00-5:00]
---
Help the user record and import their own voice for the range `$ARGUMENTS` (all cues if empty).

Before recording:
1. `python ad.py cues export --range <range> --out out/script_<range>.md` and `python ad.py build` so `out/recording_script.md` is current. Tell them to open it: each line shows the cue id, the timecode and the maximum seconds.
2. Explain the two ways to record: one file per cue named with the id (`takes/0045.wav`), or one long pass in cue order with a pause of at least one second between lines (do not read the ids aloud; after a flub, pause and read the line again). Recording in Audition at 48 kHz mono WAV is ideal; any format works.

After recording:
3. For a long pass: `python ad.py takes --file takes/<file> --range <range>`. For a folder of per-cue files: `python ad.py takes --dir takes/`.
4. If the segment count does not match, read `out/takes_report.md` with the user: identify repeated lines (flubs), write an order file listing one cue id per segment (0 to drop a segment), and rerun with `--order <file>`. Or adjust `takes.split_silence_s` / `takes.split_threshold_db` in `ad.config.json` if the split was wrong.
5. Report which takes do not fit their window (fit `no`) and offer to shorten the line or re-record just those: `python ad.py cues show --range <range> --fits no`.
6. Run `python ad.py build` and tell them to watch `out/review.mp4`.
