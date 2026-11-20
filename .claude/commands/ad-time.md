---
description: How long the process has taken so far, by phase, for the synthetic version and the recorded voice
---
Run `python ad.py timelog`. Summarise in plain language in a few lines: total hours for the synthetic version so far,
the extra hours for the recorded voice so far, the work minutes per film minute, and the one or two phases that took
longest. Then read the "Please check" section to the user and fix anything they correct:

- Time they spent away from Claude (a studio session, mixing, watching) that is missing or wrong:
  `python ad.py timelog add --phase <phase> --start "YYYY-MM-DD HH:MM" --end "HH:MM" --note "<what>"`.
  Phases: setup, draft, review, build, watching, recording, cleanup, mixing, publish, other.
- If `project/timelog.csv` does not exist or has no `prompt` rows, the logging hook is not running: check that
  `py` works in a terminal and that the hooks in `.claude/settings.json` are listed under `/hooks`.

The full report is `out/timelog.md`.
