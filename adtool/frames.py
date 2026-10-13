"""Frames for Claude to look at: storyboard sheets for a time range and a contact strip per window.

Claude Code reads image files directly, so the drafting step needs no API key.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .config import Config
from .cues import Cue, CueSheet
from .media import extract_frame, extract_frames_interval, probe
from .timecode import fmt_short, fmt_tc, range_label


def _font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # older Pillow
        return ImageFont.load_default()


def tile(items: Sequence[Tuple[str, Path]], cols: int, out_path: Path, pad: int = 6, label_h: int = 22) -> Path:
    """Tile labelled images into one JPEG sheet."""
    from PIL import Image, ImageDraw
    images = [(label, Image.open(p).convert("RGB")) for label, p in items]
    if not images:
        raise ValueError("nothing to tile")
    w = max(im.width for _, im in images)
    h = max(im.height for _, im in images)
    rows = int(math.ceil(len(images) / cols))
    sheet = Image.new("RGB", (cols * (w + pad) + pad, rows * (h + label_h + pad) + pad), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    font = _font(15)
    for k, (label, im) in enumerate(images):
        r, c = divmod(k, cols)
        x = pad + c * (w + pad)
        y = pad + r * (h + label_h + pad)
        sheet.paste(im, (x, y + label_h))
        draw.rectangle([x, y, x + w, y + label_h], fill=(40, 40, 40))
        draw.text((x + 6, y + 3), label, fill=(245, 245, 245), font=font)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(out_path), "JPEG", quality=85)
    for _, im in images:
        im.close()
    return out_path


def cue_strip(cfg: Config, video: Path, cue: Cue, out_dir: Path) -> Path:
    width = int(cfg.get("frames", "cue_width", default=480))
    n = 3 if cue.window_s <= 8 else (5 if cue.window_s <= 20 else 6)
    times = [cue.start_s + (cue.end_s - cue.start_s) * k / (n - 1) for k in range(n)]
    tmp = out_dir / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    items = []
    for k, t in enumerate(times):
        p = extract_frame(video, t, tmp / f"cue_{cue.id}_{k}.jpg", width, cfg)
        items.append((f"#{cue.id} {cue.type}  {fmt_short(t)}", p))
    out = tile(items, cols=n, out_path=out_dir / f"cue_{cue.id:04d}.jpg")
    for _, p in items:
        p.unlink(missing_ok=True)
    return out


def storyboard(cfg: Config, video: Path, start: float, end: float, out_dir: Path, label: str) -> List[Tuple[Path, float, float]]:
    f = cfg.data.get("frames", {})
    interval = float(f.get("storyboard_interval_s", 3.0))
    max_frames = int(f.get("max_storyboard_frames", 400))
    if (end - start) / interval > max_frames:
        interval = (end - start) / max_frames
    cols, rows = int(f.get("sheet_cols", 4)), int(f.get("sheet_rows", 5))
    width = int(f.get("thumb_width", 320))
    frames = extract_frames_interval(video, start, end, interval, width, out_dir / "tmp", f"sb_{label}", cfg)
    per = cols * rows
    sheets: List[Tuple[Path, float, float]] = []
    for k in range(0, len(frames), per):
        chunk = frames[k:k + per]
        items = [(fmt_short(t), p) for t, p in chunk]
        out = tile(items, cols=cols, out_path=out_dir / f"sb_{label}_{k // per + 1:02d}.jpg")
        sheets.append((out, chunk[0][0], chunk[-1][0]))
    for _, p in frames:
        p.unlink(missing_ok=True)
    return sheets


def make_packet(cfg: Config, sheet: CueSheet, start: float, end: float, with_frames: bool = True) -> Path:
    media = cfg.media_files()
    video = media["video"]
    has_video = False
    if video is not None and with_frames:
        try:
            has_video = probe(video, cfg).get("video") is not None
        except Exception:
            has_video = False
    label = range_label(start, end)
    frames_dir = cfg.work / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    sheets: List[Tuple[Path, float, float]] = []
    if has_video:
        sheets = storyboard(cfg, video, start, end, frames_dir, label)

    in_range = sheet.select(rng=f"{start}-{end}")
    for c in in_range:
        if c.type in ("DESC", "TEXT") and has_video:
            c.frame = cfg.rel(cue_strip(cfg, video, c, frames_dir))
    sheet.save()

    before = [c for c in sheet.cues if c.end_s <= start][-4:]
    glossary_path = cfg.project / "glossary.md"
    glossary = glossary_path.read_text(encoding="utf-8").strip() if glossary_path.exists() else "(no glossary yet: create project/glossary.md as names come up)"
    drafts_path = cfg.project / "drafts" / f"drafts_{label}.json"
    wps = sheet.wps

    L: List[str] = []
    L.append(f"# Draft packet {fmt_short(start)}–{fmt_short(end)}  ({cfg.get('project_name', default='Film')})\n")
    L.append(f"Reading rate assumed: {wps} words/second. Drafts file to write: `{cfg.rel(drafts_path)}`\n")
    L.append("## Steps\n")
    L.append("1. Look at every storyboard sheet below, in order, to understand what happens in this range.")
    L.append("2. For each DESC window, open its contact strip, then write one line that fits the word budget (or mark it skip with a reason).")
    L.append("3. Check SUB cues whose estimate exceeds the window; condense those lines without losing meaning.")
    L.append("4. Add TEXT cues for on-screen text that is not already a subtitle (titles, names, places, scripture references), using the storyboard timecodes.")
    L.append(f"5. Write the drafts JSON, run `python ad.py cues apply {cfg.rel(drafts_path)}`, then `python ad.py fit --range {fmt_short(start)}-{fmt_short(end)}`.\n")

    if before:
        L.append("## Just before this range (for continuity)\n")
        for c in before:
            L.append(f"- #{c.id} {c.type} {fmt_short(c.start_s)}: {c.line or '(empty)'}")
        L.append("")

    L.append("## Storyboard sheets\n")
    if sheets:
        for p, a, b in sheets:
            L.append(f"- `{cfg.rel(p)}`  covers {fmt_short(a)} – {fmt_short(b)}")
    else:
        L.append("(no video available for frames; draft from the subtitles and the user's notes)")
    L.append("")

    L.append("## Cues in this range (time order)\n")
    for c in in_range:
        est = c.est_s(wps)
        flag = "  ⚠ too long for window" if (c.type == "SUB" and est > c.window_s) else ""
        head = f"- **#{c.id} {c.type}** {fmt_short(c.start_s)}–{fmt_short(c.end_s)} ({c.window_s:.1f}s window, budget {c.budget_words(wps)} words"
        if c.type == "SUB":
            head += f", est {est:.1f}s{flag}) [{c.status}]"
            L.append(f"{head} subtitle: “{c.source_text}”")
            if c.line != c.source_text:
                L.append(f"    current line: “{c.line}”")
        else:
            head += f") [{c.status}]"
            L.append(head)
            if c.frame:
                L.append(f"    strip: `{c.frame}`")
            if c.line:
                L.append(f"    current line: “{c.line}”")
            if c.notes:
                L.append(f"    notes: {c.notes}")
    L.append("")
    L.append("## Glossary (project/glossary.md)\n")
    L.append(glossary)
    L.append("")
    L.append("## Drafts JSON format\n")
    L.append("```json")
    L.append('[\n  {"id": 12, "line": "Romulo climbs a rocky path toward a stone church.", "status": "drafted"},')
    L.append('  {"id": 13, "status": "skip", "notes": "nothing new on screen"},')
    L.append('  {"id": 7, "line": "I will go to the village tomorrow.", "notes": "condensed subtitle"},')
    L.append('  {"new": true, "type": "TEXT", "start": "1:02.0", "end": "1:05.5", "source_text": "Ayacucho, Peru 1992", "line": "Title: Ayacucho, Peru, 1992."}\n]')
    L.append("```")
    L.append("Allowed keys: id, line, status (new|drafted|approved|recorded|skip), notes, type, start, end, source_text, "
             "split_at, merge_with, remove; or new=true with type/start/end/line.")

    packets = cfg.work / "packets"
    packets.mkdir(parents=True, exist_ok=True)
    path = packets / f"packet_{label}.md"
    path.write_text("\n".join(L), encoding="utf-8")
    return path
