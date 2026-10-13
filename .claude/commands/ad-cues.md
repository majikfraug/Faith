---
description: Build (or safely rebuild) the cue sheet of subtitle reads, text reads and description windows
---
Run `python ad.py cues build`. It keeps every existing line, status and take when a sheet already exists; never pass `--force` unless the user explicitly asks to throw their work away.

Then show `python ad.py cues show --range 0:00-5:00` and explain what the three cue types are (SUB = read the subtitle over the ducked original voice, DESC = a gap where a description can go, TEXT = on-screen text to read), what `bud` (word budget) means, and that windows under about 1.5 seconds are usually left alone.

Point out how many subtitles are estimated too long for their on-screen time (the build prints this): those will need condensing during drafting.

Tell the user the next command is `/ad-draft 0:00-5:00` and that drafting goes range by range.
