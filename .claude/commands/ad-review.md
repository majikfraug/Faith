---
description: Review drafted lines in a range for accuracy, consistency and style; propose edits
argument-hint: <start-end, e.g. 0:00-5:00>
---
Review the narration in the range `$ARGUMENTS` (if empty, ask which range). Do not change anything until the user agrees.

1. `python ad.py cues show --range <range> --full` and `python ad.py frames --range <range>` (reuses existing frames quickly), then read the storyboard sheets again.
2. Check each line against the style guide (`.claude/skills/audio-description/references/style-guide.md`):
   - present tense, third person, no "we see", no camera language;
   - observation, not interpretation; no spoilers; nothing that duplicates the dialogue or subtitles;
   - names only after the film has given them; consistent with `project/glossary.md`;
   - priorities: is on-screen text covered? scene changes marked? the story-carrying action described?
   - subtitle reads: meaning and register preserved, speaker clear when voices alternate.
3. Look for windows marked skip that actually show something important, and lines that could be cut to let the music breathe.
4. Present a numbered list of proposed edits (id, current line, proposed line, reason). Keep it short; group nits.
5. When the user approves, write them to `project/drafts/review_<range>.json` and run `python ad.py cues apply <file>`, then `python ad.py fit --range <range>`. Set status `approved` on lines the user signs off.
