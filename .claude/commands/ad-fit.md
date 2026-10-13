---
description: Measure whether lines fit their windows and shorten the ones that do not
argument-hint: [range like 0:00-5:00, or --ids 12-30]
---
Run `python ad.py fit $ARGUMENTS` (no arguments means every cue). Read `out/fit_report.md`.

For each cue with fit `no`:
- if its status is `new` or `drafted`, shorten the line yourself (cut adjectives first, then clauses; keep the subject and verb; keep names and on-screen text exact), apply with `python ad.py cues set <id> --line "..."`, and re-run fit for those ids;
- if its status is `approved` or `recorded`, do not change it silently: list it for the user with the measured overage and a proposed shorter version, and ask.

`tight` means the line spills a little past the window into slack before the next speech; acceptable for descriptions, undesirable for subtitle reads. Mention them, don't rewrite them unless asked.

If TTS was unavailable and the report says estimates were used, say so and suggest running `python ad.py tts-test` to find out why.

Finish with a one-line summary: how many measured, how many fixed, what remains.
