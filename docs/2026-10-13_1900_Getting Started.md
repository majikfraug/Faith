# Getting started with the descriptive audio toolkit

This folder is a small workshop for one job: turning a finished film into a described version for YouTube.
You keep doing the parts only you can do (deciding what to say, recording your voice, polishing in Audition).
The tools and Claude take over the parts that were slow: finding every timing, counting words, pulling frames,
checking fit, and assembling the track.

## What you need on your computer

1. **Python 3.12** from python.org. On Windows tick "Add python.exe to PATH" in the installer.
2. **ffmpeg**. Windows: open a terminal and run `winget install Gyan.FFmpeg`, then open a new terminal.
   Mac: `brew install ffmpeg`. (If you get stuck, Claude can install a fallback for you.)
3. **Git** (or GitHub Desktop) so you can download the folder and save your work back.
4. **Claude Code**: the "Claude Code" extension in VS Code, or the `claude` command in a terminal. Sign in with your Claude account.
5. **Adobe Audition** for the final mix, as you already use it.

## Getting the folder

- With Git: `git clone <the repository link>` in a folder of your choice, or use GitHub Desktop, "Clone repository".
- Without Git: on the repository page, "Code" then "Download ZIP", and unzip it.

Then put the film file and its subtitle file (`.srt` or `.vtt`, the same timing as the video) into the `media/` folder.
If the subtitles only exist on YouTube, tell Claude and it will download them for you.

## Your first session

Open the folder in VS Code, start Claude Code, and type:

```
/ad-setup
```

Claude checks Python and ffmpeg, installs the packages into a private `.venv` folder, tests a synthetic voice, and
tells you what is missing. Answer its questions; this takes a few minutes once per computer. Then:

```
/ad-ingest
```

This reads the film, parses the subtitles, and listens to the whole soundtrack to find exactly where people speak.
A 67-minute film takes a few minutes on a laptop. Then:

```
/ad-cues
```

Now there is a cue sheet, `project/cues.csv`: one row per thing you will say. Three kinds:

- **SUB**: a subtitle to read aloud while the original voice is ducked underneath;
- **DESC**: a gap in the speech where a description can go, with the number of words that fit;
- **TEXT**: on-screen text to read word for word (titles, names, places, scripture references).

You never type a timecode again. The sheet opens in Excel if you want to look at it (save as "CSV UTF-8"), but it is
easier to let Claude change it for you.

## The loop, five minutes at a time

```
/ad-draft 0:00-5:00
```

Claude pulls frames from those five minutes, looks at them, and drafts a line for every description window and
every piece of on-screen text, condensing subtitles that are too long for their time on screen. It then measures
each line with a synthetic voice and shortens anything that does not fit. You get a table of the lines and a list
of questions ("is the woman at 2:14 his wife?"). Correct it in plain English:

- "Cue 45 is wrong, that is Donna, not a stranger."
- "Make 52 shorter and drop the part about the hat."
- "Skip 60, the music matters more there."
- "Say 'Sauñe' as sow-NYAY in the glossary."

Then:

```
/ad-fit            (checks timing again after edits)
/ad-build          (makes out/review.mp4: the film with a synthetic narrator, so you can hear how it plays)
/ad-review 0:00-5:00   (optional: Claude re-reads the lines against the style guide and proposes edits)
```

Watch `out/review.mp4`. Anything that sounds wrong, tell Claude. Then the next range: `/ad-draft 5:00-10:00`.
`/ad-status` always tells you where you are and what is next.

## Recording your voice

`out/recording_script.md` lists every line with its cue number, timecode and the maximum seconds it may take.
Record in Audition (48 kHz mono WAV is ideal) either:

- one file per cue, named with the cue number first (`0045.wav`, `0046 church.wav`), into `takes/`; or
- one long pass in order, leaving at least a second of silence between lines; do not read the numbers aloud.
  If you flub a line, pause and read it again, then tell Claude which one to keep.

Then `/ad-place` brings the takes in, measures each one against its window, and flags any that run long.
`/ad-build` now uses your voice where it exists and the synthetic voice elsewhere.

## Audition and YouTube

`/ad-build` gives you:

- `out/stem.wav`: your narration alone, the full length of the film. Add it as a track at 0:00 in your multitrack session.
- `out/markers_audition.csv`: every cue as a marker. Import it from the Markers panel (File > Import > Markers).
  If Audition refuses the file, export two markers from Audition to CSV and tell Claude to rebuild "like" that file.
- `out/mix_review.wav`: the original ducked under the narration, if you would rather start from a finished mix.

When every line is recorded and approved, `/ad-build --final` writes `out/final/youtube_descriptive_audio.wav`
(and an `.m4a`). In YouTube Studio, open the video, go to Languages, and add it as a descriptive audio track.
Viewers switch to it in the player's audio menu; it replaces the original audio, which is why it contains the whole mix.

## Saving and sharing your work

Say "save my work" and Claude commits the cue sheet, drafts and glossary to Git and pushes them, so the script is
backed up and others can read it. The film, frames and audio outputs stay on your computer (they are large and
can be regenerated).

## When something goes wrong

- Type `/ad-status` or ask Claude to run `python ad.py doctor`; it names what is missing.
- Timing feels wrong (lines land on speech, or gaps look too short): ask Claude to run
  `python ad.py gaps --range 12:00-13:00` and compare with the film; the voice-detection settings live in `ad.config.json`.
- The synthetic voice reads faster or slower than you: tell Claude your pace and it will adjust `timing.wps`.
- Everything can be rebuilt. Only `project/` holds your writing; keep it saved.

## Changing the tools

They are plain Python in `adtool/`. Ask Claude for changes in plain English ("add a column for who is speaking",
"make the ducking gentler for descriptions"). It edits the code, runs the tests (`python -m unittest discover -s tests`),
and you can push the change so everyone using the repository gets it.
