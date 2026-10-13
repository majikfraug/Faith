# Audio description toolkit (Faith Comes By Hearing film project)

This repository helps a narrator make a descriptive audio track for a finished film: subtitle reads,
on-screen text reads, and short visual descriptions placed in the gaps between speech, delivered as a
separate audio track on YouTube and mixed in Adobe Audition. The person you work with is the narrator
and editor. They know the film and are learning this tooling; you do the mechanical parts and draft lines
for them to approve.

## Start here

- Read `.claude/skills/audio-description/SKILL.md` before drafting, reviewing or timing anything. It holds the
  pipeline, the cue-sheet schema, the drafting procedure and the writing rules
  (full style guide in `references/style-guide.md`).
- The slash commands in `.claude/commands/` are the workflow, in order: `/ad-setup`, `/ad-ingest`, `/ad-cues`,
  `/ad-draft <range>`, `/ad-fit`, `/ad-review <range>`, `/ad-build`, `/ad-place`, `/ad-build --final`.
  `/ad-status` and `/ad-help` any time.
- Every tool is `python ad.py <command>` run from this folder (`python ad.py --help`, `python ad.py cues --help`).
  `ad.py` switches to the project's `.venv` on its own. On Windows, if `python` is not found, use `py`.

## Layout

- `adtool/`: the Python package (timecodes, subtitles, speech map, cues, frames, TTS, audio, build, takes).
- `project/cues.csv`: the cue sheet, the single source of truth. `project/glossary.md`: names and pronunciations.
  `project/drafts/`: the JSON files you write when drafting. These are committed to git.
- `media/` (the film and subtitles), `work/` (analysis, frames, TTS cache), `out/` (deliverables), `takes/`
  (recordings): large or regenerable, not in git.
- `ad.config.json`: timing, voice, ducking and path settings. `tests/`: unit tests and an end-to-end smoke test.

## Rules

- Change the cue sheet only through `python ad.py cues set|add|split|merge|skip|apply|remove`. Never rewrite
  `project/cues.csv` with the Write tool, and never run `cues build --force` unless the user asks to discard their work.
- Never place a line over speech, never invent what the frames do not show, never use a name the film has not given yet.
  When unsure who or what is on screen, ask; the user can watch the scene.
- After any batch of line edits, run `python ad.py fit` for that range and shorten what does not fit.
- Explain in plain language, one step at a time. Show lines as tables with id, time, type and line.
- When the user asks to save or share their work: `git add project ad.config.json`, commit with a short message, push.

## If something breaks

- `python ad.py doctor` first. It names the missing piece and the next step.
- Missing packages: `.venv\Scripts\python -m pip install -r requirements.txt` (Windows) or
  `.venv/bin/python -m pip install -r requirements.txt` (Mac).
- No ffmpeg: `winget install Gyan.FFmpeg` / `brew install ffmpeg`, or `pip install static-ffmpeg` in the venv.
- Voice detection fails: `python ad.py ingest --from-subtitles` as a stopgap.
- edge-tts cannot connect: built-in Windows/Mac voices are used automatically; timings are still valid.
- Audition rejects the marker file: have the user export two markers from Audition and rebuild with `--like <file>`.
- Tests: `python -m unittest discover -s tests`; end-to-end: `python tests/smoke.py` (needs ffmpeg and espeak-ng).
