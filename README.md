# Descriptive audio toolkit

Tools and Claude Code instructions for making an audio-description track for a finished film:
the narrator reads the subtitles of foreign-language dialogue, reads on-screen text, and describes what is
on screen in the gaps between speech. The result is a complete audio track for YouTube (uploaded as a
descriptive audio track) and a voice stem plus markers for Adobe Audition.

What the tools do for you:

- find every subtitle's timing from the subtitle file, and every gap in speech by listening to the soundtrack;
- compute how many words fit in each gap, and measure each draft line with a synthetic voice;
- pull frames so Claude can look at the picture and draft description lines for you to correct;
- place the narration on a film-length timeline, duck the original underneath, and write a review video,
  an Audition marker file, a recording script and, at the end, the YouTube track.

## Quick start

1. Install Python 3.12 (python.org; on Windows tick "Add python.exe to PATH"), ffmpeg
   (`winget install Gyan.FFmpeg` or `brew install ffmpeg`), Git, and Claude Code
   (VS Code extension or the `claude` command line).
2. Get this repository: `git clone <repo url>` or GitHub Desktop, or Download ZIP.
3. Open the folder in VS Code and start Claude Code. Type `/ad-setup` and follow along.
4. Put the film and its `.srt` (or `.vtt`) in `media/`.
5. Then, in order: `/ad-ingest`, `/ad-cues`, `/ad-draft 0:00-5:00`, `/ad-fit`, `/ad-build`, watch `out/review.mp4`.
   Record from `out/recording_script.md`, `/ad-place`, and finally `/ad-build --final`.

`/ad-help` explains the loop; `/ad-status` tells you where you are. The full walkthrough is in `docs/`.

## Without Claude

Everything is also a plain command: `python ad.py --help`. The order is
`init`, `ingest`, `cues build`, `frames --range`, `cues apply`, `fit`, `build`, `takes`, `build --final`.

## Layout

| Path | What |
|---|---|
| `adtool/`, `ad.py` | the Python tools |
| `.claude/commands/` | the `/ad-...` slash commands |
| `.claude/skills/audio-description/` | the workflow and the writing style guide Claude follows |
| `project/` | the cue sheet, glossary and drafts (committed) |
| `media/`, `work/`, `out/`, `takes/` | film, analysis, deliverables, recordings (not committed) |
| `tests/` | unit tests and an end-to-end smoke test on a synthetic film |
