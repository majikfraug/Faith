---
name: audio-description
description: Workflow and writing rules for making described video (audio description) for a finished film: building cue windows from subtitles and voice detection, drafting description lines that fit a time budget, reading on-screen text and subtitles aloud, checking fit with TTS, importing recorded takes, and building the YouTube audio track plus Adobe Audition markers. Use whenever the user talks about cues, windows, gaps, subtitles, narration, describing scenes, Audition, YouTube audio tracks, or the ad.py tools.
---

# Audio description for a finished film

## What we are making

A separate audio track for YouTube that replaces the film's original audio for listeners who choose it.
It contains the original soundtrack, ducked under a narrator who (1) reads the subtitles of foreign-language
dialogue, (2) reads on-screen text, and (3) briefly describes what is on screen inside gaps in the dialogue.
The film is finished, so nothing can be paused or extended: every line must fit a window that already exists.

The user is the narrator and editor. They know the film and can watch any scene. You do the mechanical work
(timing, frames, measuring, assembling) and draft lines for them to approve. Never invent what you cannot see.

## The pipeline

All commands run from the project root as `python ad.py ...` (Windows: `py ad.py ...` if `python` is missing).
`ad.py` uses the project's `.venv` automatically.

| Step | Command | Produces |
|---|---|---|
| check tools | `python ad.py doctor` | what is missing and the next step |
| ingest | `python ad.py ingest` | `work/media.json`, `work/subtitles.json`, `work/speech.json` (voice map) |
| cue windows | `python ad.py cues build` | `project/cues.csv` (keeps existing lines on rebuild; `--force` discards) |
| look at a range | `python ad.py frames --range 0:00-5:00` | storyboard sheets, per-window strips, `work/packets/packet_*.md` |
| edit cues | `python ad.py cues set/add/split/merge/skip/apply/show/export` | updated cue sheet |
| where speech is | `python ad.py gaps --range 1:00-1:30` | speech and gap listing |
| fit check | `python ad.py fit --range 0:00-5:00` | measured seconds, `out/fit_report.md` |
| review package | `python ad.py build` | `out/stem.wav`, `out/mix_review.wav`, `out/review.mp4`, `out/markers_audition.csv`, scripts |
| recorded takes | `python ad.py takes --file takes/x.wav --range ...` or `--dir takes/` | takes assigned to cues, measured |
| deliverable | `python ad.py build --final --no-tts` | `out/final/youtube_descriptive_audio.wav` + `.m4a` |
| progress | `python ad.py status` | per-block counts and the next range to draft |

Slash commands (`.claude/commands/`) wrap these in order: `/ad-setup`, `/ad-ingest`, `/ad-cues`,
`/ad-draft <range>`, `/ad-fit`, `/ad-review <range>`, `/ad-build`, `/ad-place`, `/ad-status`.

## The cue sheet (`project/cues.csv`)

One row per thing the narrator says. Edit only through `python ad.py cues ...`; never rewrite the file by hand.

- `type`: `SUB` (read a subtitle; the original speaker is ducked under it), `TEXT` (read on-screen text verbatim), `DESC` (describe).
- `start_s`/`end_s`: the window the voice may occupy. `hard_end_s`: absolute limit before the next speech.
- `window_s`, `budget_words`: window length and the word budget at `timing.wps` (default 2.5 words/second).
- `source_text`: the subtitle text or the on-screen text. `line`: what will be voiced.
- `measured_s`/`measure`: measured length of the line (`est` word-rate guess, `tts` synthetic voice, `take` the narrator's recording).
- `fits`: `yes` inside the window, `tight` spills into slack before the next speech, `no` does not fit.
- `status`: `new` → `drafted` → `approved` → `recorded`; `skip` means say nothing there.
- `frame`: the contact strip image for this window. `clip`: the recorded take. `notes`: free text.

Ids are stable. Time ranges are written `m:ss-m:ss` (e.g. `12:30-17:30`); id lists as `12-30,45`.

## Drafting a range (what `/ad-draft` does)

1. `python ad.py frames --range A-B`, then read `work/packets/packet_<range>.md`.
2. Read every storyboard sheet in order (they are images; use the Read tool). Note per timecode: who is on screen, where, what they do, any on-screen text, scene changes.
3. For each DESC window read its strip image and write one line that fits `budget_words` (fewer is better). If nothing new or useful is on screen, mark it `skip` with a short note.
4. For SUB cues flagged “too long for window”, condense the line while keeping the meaning and tone. Consider whether a listener can tell who is speaking; if not, name the speaker in the preceding DESC window, or prefix the read with the name (costs about half a second).
5. Add TEXT cues for on-screen text that is not a subtitle (titles, names, places, dates, scripture references). Place them where the text is visible and check `python ad.py gaps --range` so they never sit on speech.
6. Write the drafts JSON (format is in the packet) to `project/drafts/drafts_<range>.json`, then `python ad.py cues apply <file>` and `python ad.py fit --range A-B`.
7. For every line with `fits = no`: shorten it (adjectives first, then clauses, keep subject + verb), re-apply, re-fit. Up to three rounds; then leave a note on what still does not fit and tell the user.
8. Update `project/glossary.md` (names, places, scripture references, pronunciations, how each person was first identified).
9. Report to the user: a table of the drafted lines (id, time, type, line), every uncertainty as a question (“Is the woman at 2:14 his wife Donna?”), and the next command.

Guardrails: never place a line over speech; never invent names, relationships or intent; prefer one good line over three; do not run `cues build --force`; do not rewrite `cues.csv` with the Write tool.

## Writing rules (short form; the full guide is `references/style-guide.md`)

- Present tense, third person, plain concrete words. “Romulo lifts the book.” Never “we see”, never “the camera”.
- Say what is seen, not what it means. “She looks away” rather than “she is ashamed”, unless the film makes the feeling explicit.
- Priority when time is short: on-screen text → who is present and who is speaking → where and when → the action that carries the story → expressions and gestures → appearance and setting.
- Describe before or with the visual, never after it. Do not describe what is already audible.
- Name people the way the film does: describe them until they are named, then use the name consistently.
- On-screen text is read verbatim, introduced with a short tag (“Title:”, “Caption:”, “Text on screen:”). Scripture references are read exactly.
- Subtitle reads are neutral and clear, like a voice-over translation; the original voice stays audible underneath. Keep the subtitle's meaning and register; condense only to fit.
- Lyrics: summarize (“They sing a hymn in Quechua”) unless the words carry the story.
- No spoilers, no commentary, no filler.

## Fit, voices and rates

`fit` uses a synthetic voice to time each line (edge-tts online; Windows or macOS built-in voices offline;
espeak-ng if installed). Those are proxies for the narrator; once real takes exist, measurements use the takes.
If the narrator reads faster or slower than 2.5 words/second, change `timing.wps` in `ad.config.json`
(`python ad.py tts-test` prints the synthetic rate; divide words by seconds on a few real takes for the narrator's).

## Recording and takes

`out/recording_script.md` lists every line with its cue id, timecode and the maximum seconds. The narrator either
records one file per cue (named by id) or one long pass with a pause of at least two seconds between lines, in order.
Clean the recording (plosives, clicks, noise) in the editor *before* importing: one long file is far quicker to
clean than the split clips. `python ad.py takes --file takes/session1.wav --range 0:00-5:00` splits on silence,
matches segments to cues in order, measures, and marks them `recorded`. Clips cleaned later go in
`takes/clean/<id>.wav` and are re-imported with `python ad.py takes --dir takes/clean`. If the segment count does not match, `out/takes_report.md` lists the segments;
ask the user which to drop or re-record, or write an order file (one cue id per segment, 0 to drop) and pass `--order`.

## Delivery

`python ad.py build` makes a review package: `out/review.mp4` to watch, `out/stem.wav` (voice only, film length)
to drop into an Audition multitrack session at 0:00, `out/markers_audition.csv` to import into Audition's Markers
panel (if Audition refuses it, export two markers from Audition and rebuild with `--like <that file>`), and
`out/mix_review.wav` (original ducked under the voice). `python ad.py build --final --no-tts` writes
`out/final/youtube_descriptive_audio.wav` and `.m4a` for YouTube Studio → Languages → add audio track.
Ducking depth per type is in `ad.config.json` under `duck`. When `media/` holds a dialogue stem and a music stem
(effects optional; recognised by DIA/MX/FX or dialogue/music/effects in the file name), the build mixes from the
stems: only the dialogue is ducked under reads, music and effects pass through (dip them with `duck.MUSIC`, 0 by
default). Without stems the film's full mix is ducked under every read.

## Working with the user

Explain in plain language, one step at a time; they are learning this stack. Show lines in tables with ids and
timecodes. Ask when the frames leave a real doubt; do not guess. Keep the glossary and the cue sheet consistent.
When they ask to save their work, commit `project/` (cues, drafts, glossary) with a short message and push.
