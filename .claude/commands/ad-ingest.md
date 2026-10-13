---
description: Analyse the film: probe media, parse subtitles, detect where people speak
---
Run `python ad.py ingest` and explain the result in plain language: the film length, how many subtitles were found and how much screen time they cover, and what share of the film has speech (voice detection on the whole soundtrack, or on `media/dialogue*.wav` if present).

If voice detection fails (missing package, odd audio), run `python ad.py ingest --from-subtitles` and tell the user that gaps will then be based on subtitle timing only, which cannot protect unsubtitled English speech, so we should fix the package when possible.

If no subtitle file was found, say clearly that subtitle reads cannot be built until it exists, and continue (descriptions still work).

Then run `python ad.py gaps --range 0:00-2:00` so the user can see what the speech map looks like, and tell them the next command is `/ad-cues`.
