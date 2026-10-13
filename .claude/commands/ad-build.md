---
description: Build the review package (review video, voice stem, ducked mix, Audition markers, scripts) or the final YouTube track
argument-hint: [--final]
---
Run `python ad.py build $ARGUMENTS`. If the user said "final", run `python ad.py build --final --no-tts` instead; before that, run `python ad.py status` and warn if any cue is still `new` or `drafted` or has fit `no` (a final should only contain recorded, approved lines).

Explain the outputs in one line each:
- `out/review.mp4`: watch this; synthetic voice stands in for lines that have not been recorded.
- `out/stem.wav`: the voice track alone, film length; in Audition, add it as a track at 0:00 in the multitrack session.
- `out/mix_review.wav` (or `out/final/youtube_descriptive_audio.wav` + `.m4a`): the original ducked under the voice.
- `out/markers_audition.csv`: import in Audition's Markers panel (File > Import > Markers). If Audition refuses the file, ask the user to export two markers from Audition to a CSV, then rerun with `--like <that file>`.
- `out/recording_script.md` and `out/script.md`: what to record, and the whole script.

Read `out/build_report.md`. If it lists overlaps (a line runs into the next one), fix them: shorten the first line or split/re-time the window, then rebuild. If it lists cues without audio, say which and why.

For the final: tell the user to upload the `.wav` (or `.m4a`) in YouTube Studio under Languages as a descriptive audio track, and to listen to the whole thing once with the video before publishing.
