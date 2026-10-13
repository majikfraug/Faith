# Descriptive Audio Toolkit: Setup Guide

As of 2026-10-13

## Before you start

By the end of this guide, Claude will have drafted the first five minutes of narration for the film and you will be watching a review video of it. Set aside about an hour the first time; most of it is installing programs.

You need:

- A Windows or Mac computer where you are allowed to install programs.
- Your Claude account with a Pro or Max subscription (the same login you use for Claude today).
- A GitHub account, with the invitation to the project repository accepted (it arrives by email).
- VS Code, which you already have.
- The film as a video file (MP4 is ideal) and its subtitle file (.srt or .vtt). If the subtitles exist only on YouTube, the YouTube link is enough.

Two things to check early, because they shape the whole project: YouTube's descriptive audio track replaces the original audio, so what we make is a complete mix of the film's sound plus your voice. And the FCBH YouTube channel needs that feature available under Languages in YouTube Studio.

## Step 1. Install the four programs

Install these in order; each has a check so you know it worked. "Terminal" means the terminal inside VS Code: menu View, then Terminal. After installing anything, close VS Code and open it again so it notices the new program.

1. **Git** (Windows only; Mac already has it). Download from git-scm.com, run the installer, accept every default. Check: in a new terminal type `git --version` and a version number appears. On a Mac, type the same; if a window offers to install "command line developer tools", click Install.
2. **Python 3.12.** On python.org/downloads do not click the big download button (it gives a version too new for one of our packages). Scroll to the list of releases and pick the latest 3.12. On Windows, tick "Add python.exe to PATH" on the first screen, then Install Now. Check: in a new terminal type `python --version` (Mac: `python3 --version`) and see Python 3.12.
3. **ffmpeg** (reads and writes video and audio). Windows: in a terminal type `winget install Gyan.FFmpeg`, answer Y to the prompts, then restart VS Code. Mac: install Homebrew from brew.sh if you do not have it, then `brew install ffmpeg`. Check: `ffmpeg -version` prints a version. If this step fails, move on; the setup step has a fallback.
4. **Claude Code in VS Code.** Open Extensions (Ctrl+Shift+X, on Mac Cmd+Shift+X), search for "Claude Code" by Anthropic, click Install. Click the Claude icon that appears, choose Sign in, and log in with your Claude account (not an API key). Check: a Claude panel opens and replies when you type hello.

## Step 2. Get the project folder onto your computer

The project lives in a GitHub repository; cloning it makes a copy on your computer that can also send your work back.

1. Accept the GitHub invitation from the email, and sign in to GitHub in your browser once.
2. In VS Code press Ctrl+Shift+P (Mac: Cmd+Shift+P), type "Git: Clone", press Enter, and paste the address: https://github.com/majikfraug/Faith
3. Choose where to keep it (Documents is fine) and click Open when VS Code offers. The first time, it asks you to sign in to GitHub; pick the browser option. If it asks whether you trust the authors, say yes.
4. Check: the Explorer on the left shows a folder named Faith with `ad.py`, `adtool`, `media`, `project`, `docs` and `.claude` inside.

If "Git: Clone" is not offered, Git is not installed yet or VS Code needs a restart. GitHub Desktop (desktop.github.com) is an alternative way to clone; then open the folder in VS Code.

## Step 3. Add the film and the subtitle file

Everything about the film goes in the `media` folder inside the project. Nothing in it is ever sent to GitHub; it stays on your computer.

1. Copy the film's video file into `media`. Any name is fine. Put only one video there.
2. Copy the subtitle file (.srt or .vtt) next to it.
3. If the subtitles exist only on YouTube, skip step 2 and give Claude the YouTube link during setup; it downloads the caption track.
4. If you also have a dialogue-only audio file (voices without music and effects), copy it in with "dialogue" in its name, for example `dialogue.wav`. Voice detection becomes much more precise with it. It is optional.

## Step 4. Start Claude Code and run the setup

Claude does the installing from here; your job is to read what it proposes and say yes.

1. With the Faith folder open in VS Code, open the Claude Code panel.
2. In the message box type `/ad-setup` and press Enter. (Typing `/` shows a list of commands; pick ad-setup from it.)
3. Claude creates a private folder for the Python packages, installs them, checks ffmpeg, tests a synthetic voice and checks the media folder. Before each command it asks permission: read the line and click Allow. This is normal and only happens for new kinds of commands. Expect 5 to 10 minutes, mostly downloads.
4. It finishes with a checklist. Lines marked `[ok]` are good. For any line marked `[!!]`, Claude explains the fix; do it, then type `/ad-setup` again.
5. If `/ad-setup` is not in the list, type this instead: "Please read .claude/commands/ad-setup.md and follow it."

Check: ask Claude to run `python ad.py doctor`. Python packages, ffmpeg, a voice engine, the video and the subtitles all show `[ok]`.

## Step 5. Analyse the film

Two commands turn the film into a timing map. Nothing is written yet.

1. Type `/ad-ingest`. Claude reads the film, parses the subtitles, and listens to the whole soundtrack to find where people speak. A 67-minute film takes a few minutes. It reports the length, the number of subtitles and how much of the film has speech.
2. Type `/ad-cues`. This builds the cue sheet, `project/cues.csv`: one row per thing you will say, with its time window and how many words fit. Rows are of three kinds: SUB, a subtitle to read while the original voice is ducked; DESC, a gap where a description can go; TEXT, on-screen text to read word for word. Claude shows the first five minutes.

To look at any spot yourself, ask: "Show me the speech and gaps between 1:00 and 2:00."

## Step 6. Draft the first five minutes and watch the result

This is the test, and it is the same five-minute experiment you were doing by hand.

1. Type `/ad-draft 0:00-5:00`. Claude pulls frames from those five minutes and looks at them, drafts a line for every description window and every piece of on-screen text, condenses subtitles that are too long for their time, measures each line with a synthetic voice, and shortens what does not fit. Expect 5 to 15 minutes. It ends with a table of the lines and a few questions.
2. Answer the questions and correct anything wrong in plain English (examples in the next section).
3. Type `/ad-build`. Claude writes `out/review.mp4`: the film with a synthetic narrator reading the drafted lines over the ducked original. Open it in any video player and listen to the first five minutes.
4. Judge it: do the lines sit in the gaps, are the subtitle reads clear, is anything on screen missed? Tell Claude what is wrong; it fixes the lines and rebuilds.

When the first five minutes sound right, the pipeline works on this film, and you have a real basis for estimating the whole thing.

## How to talk to Claude about the lines

Plain English works; Claude edits the cue sheet for you, so you never need to open the spreadsheet.

- "Cue 45 is wrong. The woman is his wife Donna, not a stranger."
- "Shorten cue 52 and drop the part about the hat."
- "Skip cue 60; the music matters more there."
- "Add a line at 3:12 reading the scripture reference on screen."
- "Add to the glossary: Sauñe is pronounced sow-NYAY."
- "Show me all the lines between 2:00 and 3:00."
- "I read slower than the synthetic voice, about two words a second. Adjust the budgets."
- "Save my work." Claude sends the cue sheet, drafts and glossary to GitHub.
- "What should I do next?" or `/ad-status`.

If you prefer a spreadsheet, `project/cues.csv` opens in Excel. Save it as "CSV UTF-8" and tell Claude you edited it.

## If something goes wrong

Ask Claude to run `python ad.py doctor` first; it names the missing piece. The usual problems:

| Problem | What to do |
| --- | --- |
| "python is not recognized" | Python was installed without the PATH box ticked. Run the installer again and tick it, or on Windows tell Claude to use `py` instead. |
| ffmpeg not found after installing | Close and reopen VS Code. If still missing, ask Claude to install the fallback (static-ffmpeg). |
| A package fails to install | Your Python is probably too new. Install 3.12 and run `/ad-setup` again. |
| The voice test cannot connect | The online voice is blocked. Claude switches to the built-in Windows or Mac voice by itself; timings stay valid. |
| Claude cannot find the film or subtitles | Check that `media` holds exactly one video and one .srt or .vtt file. |
| Lines land on top of speech | Say "show me the gaps around 12:30". Claude can adjust the detection settings in `ad.config.json`. |
| "cannot write cues.csv" | The file is open in Excel. Close it and try again. |
| A `/ad-` command is not in the list | Tell Claude to read the matching file in `.claude/commands` and follow it. |

For anything else, paste the error to Claude and ask it to explain in plain words what happened and what to try.

## What comes after the test

Once the first five minutes sound right, the rest is repetition: `/ad-draft 5:00-10:00` and so on, `/ad-review` on a range to polish it, then recording from `out/recording_script.md`, `/ad-place` to bring your takes in, and `/ad-build --final` for the YouTube track. The voice stem and the marker file go into Audition if you want to polish the mix there.

The fuller guide for those steps is in the project: `docs/2026-10-13_1900_Getting Started.md`.
