"""Command-line interface: python ad.py <command> ..."""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from . import config as C
from .timecode import fmt_short, fmt_tc, parse_ids, parse_range, parse_tc


def _ok(msg: str) -> None:
    print(f"  [ok] {msg}")


def _warn(msg: str) -> None:
    print(f"  [!!] {msg}")


# ---------------------------------------------------------------------------
# doctor / init
# ---------------------------------------------------------------------------

def cmd_init(args) -> int:
    root = C.find_root()
    path = root / C.CONFIG_NAME
    if path.exists() and not args.force:
        print(f"{C.CONFIG_NAME} already exists at {root}")
    else:
        C.write_default(root)
        print(f"wrote {path}")
    for d in ("media", "work", "out", "takes", "project", "project/drafts"):
        (root / d).mkdir(parents=True, exist_ok=True)
    print("folders ready: media/ (put the film + subtitles here), takes/ (your recordings), project/ (cue sheet), work/, out/")
    return 0


def cmd_doctor(args) -> int:
    cfg = C.load()
    print(f"adtool {__version__}  python {platform.python_version()}  {platform.system()} {platform.release()}")
    print(f"project root: {cfg.root}")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    (_ok if in_venv else _warn)(f"interpreter: {sys.executable}" + ("" if in_venv else "  (not the project .venv)"))
    problems = 0
    for mod, pipname, required in (("numpy", "numpy", True), ("soundfile", "soundfile", True), ("PIL", "Pillow", True),
                                   ("faster_whisper", "faster-whisper", True), ("edge_tts", "edge-tts", False)):
        found = importlib.util.find_spec(mod) is not None
        if found:
            _ok(f"{pipname} installed")
        elif required:
            _warn(f"{pipname} missing  ->  pip install {pipname}")
            problems += 1
        else:
            _warn(f"{pipname} missing (optional: free neural TTS voice)  ->  pip install {pipname}")
    try:
        from .media import find_ffmpeg, run
        ff, fp = find_ffmpeg(cfg)
        ver = run([ff, "-version"]).stdout.splitlines()[0]
        _ok(f"ffmpeg: {ver[:60]}")
    except Exception as e:
        _warn(str(e))
        problems += 1
    from . import tts
    engines = tts.available_engines()
    if engines:
        _ok("TTS engines available: " + ", ".join(engines) + f"  (configured: {cfg.get('tts', 'engine', default='auto')})")
    else:
        _warn("no TTS engine available: fit checks will use word-rate estimates only")
    media = cfg.media_files()
    for key in ("video", "subtitles", "audio", "dialogue"):
        p = media[key]
        if p is not None:
            _ok(f"{key}: {cfg.rel(p)}")
        elif key in ("video", "subtitles"):
            _warn(f"{key}: not found (put it in media/ or set media.{key} in {C.CONFIG_NAME})")
    if not (cfg.root / C.CONFIG_NAME).exists():
        _warn(f"no {C.CONFIG_NAME} yet: run `python ad.py init`")
    if (cfg.work / "speech.json").exists():
        _ok("speech map exists (work/speech.json)")
    else:
        print("  next: python ad.py ingest")
    if cfg.cues_path.exists():
        _ok(f"cue sheet exists ({cfg.rel(cfg.cues_path)})")
    elif (cfg.work / "speech.json").exists():
        print("  next: python ad.py cues build")
    return 1 if problems else 0


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

def cmd_ingest(args) -> int:
    from .media import probe
    from .speech import build_speech_map, mix_source, transcribe
    from .subtitles import parse_subtitles, save_json

    cfg = C.load()
    media = cfg.media_files()
    src = media["audio"] or media["video"]
    if src is None:
        print("no film found. Put the video (or audio) file in media/ or set media.video in ad.config.json")
        return 1
    info = probe(src, cfg)
    if media["video"] is not None and media["video"] != src:
        vinfo = probe(media["video"], cfg)
        info["video_file"] = str(media["video"])
        info["video"] = vinfo.get("video")
    (cfg.work / "media.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    duration = float(info["duration"])
    print(f"film: {cfg.rel(src)}  duration {fmt_tc(duration)}  "
          + (f"video {info['video']['width']}x{info['video']['height']} @ {info['video']['fps']} fps  " if info.get("video") else "(no video stream)  ")
          + (f"audio {info['audio']['sample_rate']} Hz x{info['audio']['channels']}" if info.get("audio") else "NO AUDIO"))

    subs = []
    if media["subtitles"] is not None:
        subs = parse_subtitles(media["subtitles"])
        save_json(subs, cfg.work / "subtitles.json")
        total = sum(s.end - s.start for s in subs)
        print(f"subtitles: {len(subs)} cues from {cfg.rel(media['subtitles'])}, {total:.0f}s on screen")
    else:
        print("subtitles: none found (SUB cues will not be created). Add the .srt/.vtt to media/ when you have it.")

    if args.from_subtitles and not subs:
        print("--from-subtitles needs a subtitle file")
        return 1
    print("speech map: " + ("from subtitle timing" if args.from_subtitles else "running voice detection on the soundtrack ..."))
    sm = build_speech_map(cfg, duration, from_subtitles=args.from_subtitles, subs=subs)
    st = sm["stats"]
    print(f"speech: {st['segments']} segments, {st['speech_s']:.0f}s ({st['speech_pct']}% of the film) -> work/speech.json")
    if args.transcribe:
        print(f"transcribing with whisper '{args.model}' (this can take a while on CPU) ...")
        p = transcribe(cfg, args.model, args.language)
        print(f"transcript -> {cfg.rel(p)}")
    print("next: python ad.py cues build")
    return 0


# ---------------------------------------------------------------------------
# cues
# ---------------------------------------------------------------------------

def _load_sheet(cfg):
    from .cues import CueSheet
    return CueSheet.load(cfg)


def cmd_cues_build(args) -> int:
    from .cues import CueSheet, build_cues, merge_existing, read_csv
    from .speech import load_speech
    from .subtitles import load_json

    cfg = C.load()
    speech = load_speech(cfg)
    duration = float(speech.get("duration") or 0.0)
    subs_path = cfg.work / "subtitles.json"
    subs = load_json(subs_path) if subs_path.exists() else []
    segs = [(s["start"], s["end"]) for s in speech["segments"]]
    cues = build_cues(cfg, subs, segs, duration)
    sheet = CueSheet(cfg, cues)
    if cfg.cues_path.exists():
        if args.force:
            print("rebuilding from scratch (--force): previous lines and statuses are discarded")
        else:
            old = read_csv(cfg.cues_path)
            merged, stats = merge_existing(cues, old)
            sheet = CueSheet(cfg, merged)
            print(f"merged with existing sheet: kept {stats['kept']}, added {stats['added']}, orphaned {stats['orphaned']}")
    sheet.save()
    s = sheet.summary()
    print(f"cue sheet -> {cfg.rel(cfg.cues_path)}: {s['total']} cues  "
          + ", ".join(f"{k} {v}" for k, v in sorted(s["by_type"].items())))
    print(f"description windows total {s['desc_seconds']:.0f}s; subtitles estimated too long for their window: {s['sub_est_no']}")
    print("next: python ad.py frames --range 0:00-5:00   (then draft from the packet)")
    return 0


def cmd_cues_show(args) -> int:
    cfg = C.load()
    sheet = _load_sheet(cfg)
    cues = sheet.select(args.range, args.ids, args.type, args.status, args.fits)
    if not cues:
        print("no cues match")
        return 0
    print(sheet.table(cues, width=400 if args.full else 72))
    print(f"{len(cues)} cue(s)")
    return 0


def cmd_cues_set(args) -> int:
    cfg = C.load()
    sheet = _load_sheet(cfg)
    c = sheet.set(args.id, line=args.line, status=args.status, notes=args.notes, type_=args.type,
                  start=parse_tc(args.start) if args.start else None, end=parse_tc(args.end) if args.end else None,
                  source_text=args.source, append_note=args.append_note)
    sheet.save()
    print(f"{c.label()} [{c.status}] {c.window_s:.1f}s budget {c.budget_words(sheet.wps)}: {c.line}")
    return 0


def cmd_cues_add(args) -> int:
    cfg = C.load()
    sheet = _load_sheet(cfg)
    c = sheet.add(args.type, parse_tc(args.start), parse_tc(args.end), line=args.line or "", source_text=args.source or "",
                  status=args.status, notes=args.notes or "")
    sheet.save()
    print(f"added {c.label()} {c.window_s:.1f}s budget {c.budget_words(sheet.wps)}: {c.line}")
    return 0


def cmd_cues_split(args) -> int:
    cfg = C.load()
    sheet = _load_sheet(cfg)
    a, b = sheet.split(args.id, parse_tc(args.at))
    sheet.save()
    print(f"split: {a.label()} ({a.window_s:.1f}s) and {b.label()} ({b.window_s:.1f}s)")
    return 0


def cmd_cues_merge(args) -> int:
    cfg = C.load()
    sheet = _load_sheet(cfg)
    c = sheet.merge(args.id, args.id2)
    sheet.save()
    print(f"merged into {c.label()} ({c.window_s:.1f}s): {c.line}")
    return 0


def cmd_cues_remove(args) -> int:
    cfg = C.load()
    sheet = _load_sheet(cfg)
    sheet.remove(args.id)
    sheet.save()
    print(f"removed #{args.id}")
    return 0


def cmd_cues_skip(args) -> int:
    cfg = C.load()
    sheet = _load_sheet(cfg)
    for cid in sorted(parse_ids(args.ids)):
        sheet.set(cid, status="new" if args.undo else "skip", notes=args.note, append_note=True)
    sheet.save()
    print(("un-skipped " if args.undo else "skipped ") + args.ids)
    return 0


def cmd_cues_apply(args) -> int:
    cfg = C.load()
    sheet = _load_sheet(cfg)
    path = Path(args.file)
    try:
        ops = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        print(f"{path} is not valid JSON: {e}")
        return 1
    if isinstance(ops, dict):
        ops = ops.get("cues") or ops.get("drafts") or [ops]
    log = sheet.apply(ops)
    sheet.save()
    for line in log:
        print("  " + line)
    print(f"applied {len(log)} change(s) -> {cfg.rel(cfg.cues_path)}")
    return 0


def cmd_cues_export(args) -> int:
    cfg = C.load()
    sheet = _load_sheet(cfg)
    cues = sheet.select(args.range) if args.range else sheet.cues
    md = sheet.script_markdown(cues)
    out = Path(args.out) if args.out else cfg.out / "script.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"wrote {cfg.rel(out)} ({sum(1 for c in cues if c.status != 'skip')} lines)")
    return 0


def cmd_gaps(args) -> int:
    from .speech import load_speech
    cfg = C.load()
    sp = load_speech(cfg)
    a, b = parse_range(args.range, sp["duration"])
    b = b if b is not None else sp["duration"]
    segs = [(s["start"], s["end"]) for s in sp["segments"] if s["end"] > a and s["start"] < b]
    print(f"speech between {fmt_short(a)} and {fmt_short(b)} (source: {sp['source']}):")
    prev = a
    for s, e in segs:
        if s - prev >= 0.5:
            print(f"      gap  {fmt_short(prev)} - {fmt_short(s)}  ({s - prev:.1f}s)")
        print(f"   speech  {fmt_short(s)} - {fmt_short(e)}  ({e - s:.1f}s)")
        prev = e
    if b - prev >= 0.5:
        print(f"      gap  {fmt_short(prev)} - {fmt_short(b)}  ({b - prev:.1f}s)")
    return 0


# ---------------------------------------------------------------------------
# frames / fit / build / takes / status / tts
# ---------------------------------------------------------------------------

def cmd_frames(args) -> int:
    from .frames import make_packet
    cfg = C.load()
    sheet = _load_sheet(cfg)
    a, b = parse_range(args.range, sheet.duration_hint())
    if b is None:
        b = sheet.duration_hint()
    path = make_packet(cfg, sheet, a, b, with_frames=not args.no_frames)
    print(f"draft packet -> {cfg.rel(path)}")
    print("next: read the packet, look at the sheets, write the drafts JSON, then `python ad.py cues apply <file>`")
    return 0


def cmd_fit(args) -> int:
    from .fit import run_fit
    cfg = C.load()
    sheet = _load_sheet(cfg)
    cues = sheet.select(args.range, args.ids) if (args.range or args.ids) else sheet.cues
    res = run_fit(cfg, sheet, cues, engine=args.engine, estimate_only=args.estimate)
    print(f"measured {res['measured']} cue(s) using {res['engine']}: {res['no']} do not fit, {res['tight']} tight")
    for c in res["problems"][:40]:
        print(f"  #{c.id} {c.type} {fmt_short(c.start_s)} window {c.window_s:.1f}s measured {c.measured_s:.1f}s "
              f"[{c.fits}] cut ≈{int(round(c.overage_s() * sheet.wps + 0.49))} words: {c.line[:70]}")
    print(f"report -> {cfg.rel(res['report'])}")
    return 0


def cmd_build(args) -> int:
    from .build import build
    cfg = C.load()
    sheet = _load_sheet(cfg)
    res = build(cfg, sheet, final=args.final, allow_tts=not args.no_tts, with_video=not args.no_video,
                like=Path(args.like) if args.like else None, engine=args.engine)
    print(f"stem   -> {cfg.rel(res['stem'])}")
    print(f"mix    -> {cfg.rel(res['mix'])}   (peak {res['peak_db']} dBFS, clipped samples {res['clipped']})")
    if res.get("m4a"):
        print(f"m4a    -> {cfg.rel(res['m4a'])}   (upload this or the wav to YouTube)")
    if res.get("review_mp4"):
        print(f"review -> {cfg.rel(res['review_mp4'])}   (watch this)")
    if res.get("review_error"):
        print(f"review video not written: {res['review_error']}")
    print(f"markers-> {cfg.rel(res['markers'])}   (Audition: Markers panel > import)")
    print(f"placed {res['takes']} recorded take(s) and {res['tts']} synthetic line(s); {len(res['missing'])} cue(s) without audio; "
          f"{len(res['collisions'])} overlap(s)")
    for m in res["collisions"][:20]:
        print("  overlap: " + m)
    print(f"report -> {cfg.rel(res['report'])}")
    return 0


def cmd_takes(args) -> int:
    from .takes import import_dir, import_long_take
    cfg = C.load()
    sheet = _load_sheet(cfg)
    if args.dir:
        for line in import_dir(cfg, sheet, Path(args.dir)):
            print("  " + line)
        return 0
    targets = sheet.select(args.range, args.ids) if (args.range or args.ids) else sheet.cues
    order = None
    if args.order:
        order = [int(x) for x in Path(args.order).read_text(encoding="utf-8").split()]
    res = import_long_take(cfg, sheet, Path(args.file), targets, order)
    if not res["ok"]:
        print(f"found {res['segments']} spoken segments but expected {res['expected']} lines; see {cfg.rel(res['report'])}")
        return 1
    for line in res["assigned"]:
        print("  " + line)
    print(f"assigned {len(res['assigned'])} take(s). next: python ad.py build")
    return 0


def cmd_status(args) -> int:
    from .report import status_markdown
    cfg = C.load()
    sheet = _load_sheet(cfg)
    md = status_markdown(cfg, sheet)
    (cfg.out / "status.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


def cmd_tts_test(args) -> int:
    from . import tts
    cfg = C.load()
    print("engines available: " + (", ".join(tts.available_engines()) or "none"))
    try:
        if args.text:
            path, used = tts.synth(cfg, args.text, args.engine)
            dur = tts.measure(path)
        else:
            path, used, dur = tts.test_voice(cfg, args.engine)
        print(f"{used}: {dur:.2f}s for {len((args.text or tts.SAMPLE_TEXT).split())} words -> {cfg.rel(path)}")
        print(f"that is {len((args.text or tts.SAMPLE_TEXT).split()) / dur:.2f} words/second (timing.wps in ad.config.json is {cfg.get('timing', 'wps')})")
    except tts.TTSError as e:
        print(f"TTS failed: {e}")
        return 1
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ad.py", description="Audio description toolkit")
    p.add_argument("--version", action="version", version=f"adtool {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create ad.config.json and the project folders")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("doctor", help="check tools, packages, media and what to do next")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("ingest", help="probe the film, parse subtitles, build the speech map")
    s.add_argument("--from-subtitles", action="store_true", help="use subtitle timing instead of voice detection")
    s.add_argument("--transcribe", action="store_true", help="also transcribe the soundtrack with whisper (slow)")
    s.add_argument("--model", default="small")
    s.add_argument("--language", default=None)
    s.set_defaults(fn=cmd_ingest)

    c = sub.add_parser("cues", help="build and edit the cue sheet (project/cues.csv)")
    cs = c.add_subparsers(dest="sub", required=True)
    s = cs.add_parser("build", help="create windows from subtitles + speech map (keeps existing lines)")
    s.add_argument("--force", action="store_true", help="discard the existing sheet")
    s.set_defaults(fn=cmd_cues_build)
    s = cs.add_parser("show", help="list cues")
    s.add_argument("--range"); s.add_argument("--ids"); s.add_argument("--type"); s.add_argument("--status"); s.add_argument("--fits")
    s.add_argument("--full", action="store_true", help="do not truncate lines")
    s.set_defaults(fn=cmd_cues_show)
    s = cs.add_parser("set", help="edit one cue")
    s.add_argument("id", type=int)
    s.add_argument("--line"); s.add_argument("--status"); s.add_argument("--notes"); s.add_argument("--append-note", action="store_true")
    s.add_argument("--type"); s.add_argument("--start"); s.add_argument("--end"); s.add_argument("--source")
    s.set_defaults(fn=cmd_cues_set)
    s = cs.add_parser("add", help="add a cue (e.g. on-screen TEXT)")
    s.add_argument("--type", required=True); s.add_argument("--start", required=True); s.add_argument("--end", required=True)
    s.add_argument("--line"); s.add_argument("--source"); s.add_argument("--status", default="drafted"); s.add_argument("--notes")
    s.set_defaults(fn=cmd_cues_add)
    s = cs.add_parser("split", help="split a window at a time")
    s.add_argument("id", type=int); s.add_argument("--at", required=True)
    s.set_defaults(fn=cmd_cues_split)
    s = cs.add_parser("merge", help="merge two cues into the first")
    s.add_argument("id", type=int); s.add_argument("id2", type=int)
    s.set_defaults(fn=cmd_cues_merge)
    s = cs.add_parser("remove", help="delete a cue (prefer skip)")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_cues_remove)
    s = cs.add_parser("skip", help="mark cues as skip (nothing to say there)")
    s.add_argument("ids"); s.add_argument("--note"); s.add_argument("--undo", action="store_true")
    s.set_defaults(fn=cmd_cues_skip)
    s = cs.add_parser("apply", help="apply a drafts JSON file")
    s.add_argument("file")
    s.set_defaults(fn=cmd_cues_apply)
    s = cs.add_parser("export", help="write the script as markdown")
    s.add_argument("--range"); s.add_argument("--out")
    s.set_defaults(fn=cmd_cues_export)

    s = sub.add_parser("gaps", help="show speech and gaps in a time range")
    s.add_argument("--range", default="all")
    s.set_defaults(fn=cmd_gaps)

    s = sub.add_parser("frames", help="make storyboard sheets + a draft packet for a time range")
    s.add_argument("--range", required=True, help="e.g. 0:00-5:00")
    s.add_argument("--no-frames", action="store_true")
    s.set_defaults(fn=cmd_frames)

    s = sub.add_parser("fit", help="measure each line against its window")
    s.add_argument("--range"); s.add_argument("--ids"); s.add_argument("--engine")
    s.add_argument("--estimate", action="store_true", help="word-rate estimate only, no TTS")
    s.set_defaults(fn=cmd_fit)

    s = sub.add_parser("build", help="render stem, review mix, review video, Audition markers, scripts")
    s.add_argument("--final", action="store_true", help="write out/final/ for YouTube")
    s.add_argument("--no-tts", action="store_true", help="only use recorded takes")
    s.add_argument("--no-video", action="store_true")
    s.add_argument("--like", help="an exported Audition marker file to copy the format from")
    s.add_argument("--engine")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("takes", help="import recorded takes")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", help="one long recording, lines in cue order separated by pauses")
    g.add_argument("--dir", help="folder of one-file-per-cue recordings named by cue id")
    s.add_argument("--range"); s.add_argument("--ids"); s.add_argument("--order", help="text file: one cue id per segment")
    s.set_defaults(fn=cmd_takes)

    s = sub.add_parser("status", help="progress by 5-minute block and the next range to draft")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("tts-test", help="synthesize a sample line and report the reading rate")
    s.add_argument("--engine"); s.add_argument("--text")
    s.set_defaults(fn=cmd_tts_test)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code)
            return 1
        raise
    except KeyboardInterrupt:
        print("interrupted")
        return 130
    except Exception as e:  # keep errors readable for a non-programmer
        from .cues import CueError
        from .media import MediaError
        if isinstance(e, (CueError, MediaError, ValueError)):
            print(f"error: {e}")
            return 1
        raise
