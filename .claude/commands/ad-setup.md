---
description: First-time setup on this computer (Python environment, packages, ffmpeg, voice test, media check)
---
Set this project up on the user's computer. Go step by step, say in one plain sentence what each step does, and only stop to ask when a real choice is theirs. The user is learning this stack; avoid jargon.

1. Find out the operating system and Python. Run `python --version` (on Windows also try `py -3 --version`). We need Python 3.10 to 3.13 (3.14 may not have wheels for faster-whisper yet). If Python is missing or too new, tell them how to install 3.12: Windows from python.org (tick "Add python.exe to PATH"), Mac `brew install python@3.12`. Then start again.
2. Create the virtual environment if `.venv` does not exist: `python -m venv .venv` (Windows with several Pythons: `py -3.12 -m venv .venv`).
3. Install packages using the venv's own Python: Windows `.venv\Scripts\python -m pip install -r requirements.txt`, Mac/Linux `.venv/bin/python -m pip install -r requirements.txt`. If faster-whisper fails to install, retry once; if it still fails, continue (voice detection can fall back to subtitle timing) and say so.
4. Check ffmpeg with `ffmpeg -version`. If missing: Windows `winget install Gyan.FFmpeg` then open a new terminal; Mac `brew install ffmpeg`. If neither is possible, `.venv\Scripts\python -m pip install static-ffmpeg` (it downloads ffmpeg on first use).
5. Run `python ad.py init`, then `python ad.py doctor`, and fix anything marked `[!!]`.
6. Media: the film file and its subtitle file (.srt or .vtt) go in `media/`. If the subtitles live only on YouTube, install yt-dlp in the venv and run `yt-dlp --write-subs --sub-langs en --skip-download -o "media/film" <url>`. If the subtitles are burned into the picture and no file exists, stop and tell the user we need the subtitle file from whoever made the film. If they have a dialogue-only audio stem, put it in `media/` with "dialogue" or "DIA" in the name; it makes voice detection much better. If they also have music and effects stems, put those in `media/` too ("music"/"MX", "effects"/"FX" in the names): the build then ducks only the dialogue and leaves music and effects clean.
7. Set `project_name` in `ad.config.json` to the film's name.
8. Test the synthetic voice: `python ad.py tts-test`. Report which engine worked and the measured words per second. If edge-tts cannot reach the internet, Windows and Mac built-in voices are used automatically.
9. Finish by running `python ad.py doctor` again and telling the user the next command is `/ad-ingest`.
