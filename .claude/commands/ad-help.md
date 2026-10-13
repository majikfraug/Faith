---
description: Explain the whole workflow in plain language and what to do next
---
Explain, in plain language and no more than a screen of text, how this project works: the film is finished; we make a separate YouTube audio track where a narrator reads the subtitles, reads on-screen text, and describes what is on screen in the gaps between speech. Then the loop:

1. `/ad-setup` once per computer.  2. `/ad-ingest` once per film.  3. `/ad-cues` builds the cue sheet.
4. `/ad-draft 0:00-5:00`, five minutes at a time: Claude looks at frames and drafts lines; you correct them.
5. `/ad-fit` checks timing.  6. `/ad-build` makes a review video to watch.  7. `/ad-review` polishes a range.
8. Record from `out/recording_script.md`, then `/ad-place` to bring the takes in.  9. `/ad-build --final` for YouTube.

Then run `python ad.py status` (or say it is not set up yet) and tell the user the single next command to type.
