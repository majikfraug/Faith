---
description: Draft the lines for a time range (e.g. /ad-draft 5:00-10:00) by looking at the frames
argument-hint: <start-end, e.g. 0:00-5:00>
---
Draft the narration for the range `$ARGUMENTS` (if empty, run `python ad.py status` and use the "next range to draft"). Load the `audio-description` skill rules first if they are not already in context, and keep `.claude/skills/audio-description/references/style-guide.md` in mind.

Procedure:
1. `python ad.py frames --range <range>` and read the packet it names in `work/packets/`.
2. Read every storyboard sheet listed, in order, with the Read tool. Write yourself a short timeline: who is on screen, where, what happens, any on-screen text (with the timecode from the frame labels), scene changes.
3. For each DESC cue in the packet, read its strip image and write one line within its word budget, following the writing rules (present tense, what is visible, priorities, no interpretation, no "we see"). If there is nothing worth saying, set status `skip` with a short note.
4. For SUB cues marked too long, condense the line, keeping meaning and register. Where a listener could not tell who is speaking, name the speaker in the preceding DESC line or prefix the read with the name.
5. Create TEXT cues for on-screen text that is not a subtitle (titles, names, places, dates, scripture references). Use `python ad.py gaps --range` to make sure the window is not on speech.
6. Write the JSON to `project/drafts/drafts_<range>.json` (format is in the packet), run `python ad.py cues apply <file>`, then `python ad.py fit --range <range>`.
7. Shorten anything with fit `no` (adjectives first, then clauses, keep subject and verb), re-apply, re-fit. Up to three rounds; then note what still does not fit.
8. Update `project/glossary.md` with any new names, places, references and how each person was first identified.
9. Report: a table of the drafted lines (id, time, type, line) and a short list of questions where the frames left you unsure (the user can watch the scene). Suggest `/ad-build` to make a review video of what exists so far, or the next range.

Never invent names or relationships, never put a line over speech, never run `cues build --force`, never edit `project/cues.csv` by rewriting the file.
