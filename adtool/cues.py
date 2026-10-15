"""The cue sheet: one row per thing the narrator will say, with its time window.

Types
  SUB   read a subtitle (the window is the subtitle's on-screen time; the original speaker is ducked under it)
  TEXT  read on-screen text (titles, captions, scripture references) verbatim
  DESC  describe what is on screen, inside a gap in the dialogue

project/cues.csv is the single source of truth. Edit it through these tools
(or carefully in a spreadsheet, saving as CSV UTF-8). The *_s columns are
authoritative; the *_tc columns are regenerated for reading.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .config import Config
from .subtitles import Subtitle
from .timecode import fmt_short, fmt_tc, parse_ids, parse_range, parse_tc

TYPES = ("SUB", "TEXT", "DESC")
STATUSES = ("new", "drafted", "approved", "recorded", "skip")
COLUMNS = ["id", "type", "start_tc", "end_tc", "start_s", "end_s", "hard_end_s", "window_s", "budget_words",
           "source_text", "line", "words", "est_s", "measured_s", "measure", "fits", "status", "clip", "frame", "notes"]


class CueError(ValueError):
    pass


@dataclass
class Cue:
    id: int
    type: str
    start_s: float
    end_s: float
    hard_end_s: float
    source_text: str = ""
    line: str = ""
    measured_s: Optional[float] = None
    measure: str = ""          # "", est, tts, take
    fits: str = ""             # "", yes, tight, no
    status: str = "new"
    clip: str = ""             # recorded take (project-relative path) when measure == take
    frame: str = ""            # contact strip image for this window
    notes: str = ""

    # ----- derived ----------------------------------------------------
    @property
    def window_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)

    @property
    def hard_s(self) -> float:
        return max(self.window_s, self.hard_end_s - self.start_s)

    @property
    def words(self) -> int:
        return len(self.line.split())

    def budget_words(self, wps: float) -> int:
        return int(math.floor(self.window_s * wps + 1e-6))

    def est_s(self, wps: float) -> float:
        return round(self.words / wps, 2) if wps > 0 else 0.0

    def recompute_fit(self) -> None:
        if self.measured_s is None:
            self.fits = ""
            return
        if self.measured_s <= self.window_s + 1e-6:
            self.fits = "yes"
        elif self.measured_s <= self.hard_s + 1e-6:
            self.fits = "tight"
        else:
            self.fits = "no"

    def overage_s(self) -> float:
        if self.measured_s is None:
            return 0.0
        return max(0.0, self.measured_s - self.window_s)

    def label(self) -> str:
        return f"#{self.id} {self.type} {fmt_short(self.start_s)}"


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def _f(v, default=None):
    if v is None:
        return default
    s = str(v).strip()
    if s == "":
        return default
    try:
        return float(s)
    except ValueError:
        try:
            return parse_tc(s)
        except ValueError:
            return default


def read_csv(path: Path) -> List[Cue]:
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    rows = list(csv.DictReader(text.splitlines()))
    cues: List[Cue] = []
    for r in rows:
        try:
            cid = int(float(str(r.get("id", "")).strip()))
        except ValueError:
            continue
        start = _f(r.get("start_s"), None)
        end = _f(r.get("end_s"), None)
        if start is None and r.get("start_tc"):
            start = _f(r.get("start_tc"))
        if end is None and r.get("end_tc"):
            end = _f(r.get("end_tc"))
        if start is None or end is None:
            raise CueError(f"cue {cid}: missing start/end")
        hard = _f(r.get("hard_end_s"), end)
        measured = _f(r.get("measured_s"), None)
        cue = Cue(
            id=cid,
            type=(r.get("type") or "DESC").strip().upper(),
            start_s=start, end_s=end, hard_end_s=max(hard, end),
            source_text=(r.get("source_text") or "").strip(),
            line=(r.get("line") or "").strip(),
            measured_s=measured,
            measure=(r.get("measure") or "").strip(),
            fits=(r.get("fits") or "").strip(),
            status=(r.get("status") or "new").strip().lower() or "new",
            clip=(r.get("clip") or "").strip(),
            frame=(r.get("frame") or "").strip(),
            notes=(r.get("notes") or "").strip(),
        )
        if cue.type not in TYPES:
            raise CueError(f"cue {cid}: unknown type {cue.type}")
        cues.append(cue)
    cues.sort(key=lambda c: (c.start_s, c.id))
    return cues


def write_csv(path: Path, cues: Sequence[Cue], wps: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for c in sorted(cues, key=lambda c: (c.start_s, c.id)):
            w.writerow({
                "id": c.id, "type": c.type,
                "start_tc": fmt_tc(c.start_s), "end_tc": fmt_tc(c.end_s),
                "start_s": f"{c.start_s:.3f}", "end_s": f"{c.end_s:.3f}", "hard_end_s": f"{c.hard_end_s:.3f}",
                "window_s": f"{c.window_s:.2f}", "budget_words": c.budget_words(wps),
                "source_text": c.source_text, "line": c.line, "words": c.words, "est_s": f"{c.est_s(wps):.2f}",
                "measured_s": "" if c.measured_s is None else f"{c.measured_s:.2f}",
                "measure": c.measure, "fits": c.fits, "status": c.status,
                "clip": c.clip, "frame": c.frame, "notes": c.notes,
            })
    try:
        tmp.replace(path)
    except PermissionError:
        raise CueError(f"cannot write {path.name}: it is probably open in Excel or another program. Close it and retry.")
    return path


# ---------------------------------------------------------------------------
# Building windows from subtitles + speech map
# ---------------------------------------------------------------------------

def merge_subtitles(subs: List[Subtitle], gap_s: float, max_s: float) -> List[Tuple[float, float, str, List[int]]]:
    """Join a subtitle with the next one when it is clearly an unfinished sentence."""
    out: List[List] = []
    enders = tuple(".?!…\"”»)]")
    for s in subs:
        if out:
            p_start, p_end, p_text, p_ids = out[-1]
            unfinished = not p_text.rstrip().endswith(enders)
            if unfinished and s.start - p_end < gap_s and s.end - p_start <= max_s:
                out[-1] = [p_start, max(p_end, s.end), f"{p_text} {s.text}", p_ids + [s.index]]
                continue
        out.append([s.start, s.end, s.text, [s.index]])
    return [tuple(x) for x in out]


def union_intervals(intervals: Iterable[Tuple[float, float]], min_gap: float = 0.0) -> List[Tuple[float, float]]:
    items = sorted((float(a), float(b)) for a, b in intervals if b > a)
    out: List[List[float]] = []
    for a, b in items:
        if out and a - out[-1][1] <= min_gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def complement(intervals: List[Tuple[float, float]], total: float) -> List[Tuple[float, float]]:
    gaps: List[Tuple[float, float]] = []
    cur = 0.0
    for a, b in intervals:
        if a > cur:
            gaps.append((cur, a))
        cur = max(cur, b)
    if total > cur:
        gaps.append((cur, total))
    return gaps


def build_cues(cfg: Config, subs: List[Subtitle], speech: List[Tuple[float, float]], duration: float) -> List[Cue]:
    t = cfg.data.get("timing", {})
    merged = merge_subtitles(subs, float(t.get("sub_merge_gap_s", 0.3)), float(t.get("sub_merge_max_s", 7.0)))
    cues: List[Cue] = []
    for k, (start, end, text, ids) in enumerate(merged):
        next_start = merged[k + 1][0] if k + 1 < len(merged) else duration
        hard_end = max(end, next_start - 0.1)
        note = f"subs {ids[0]}-{ids[-1]} merged" if len(ids) > 1 else ""
        cues.append(Cue(0, "SUB", start, end, hard_end, source_text=text, line=text, notes=note))

    busy = union_intervals(list(speech) + [(c.start_s, c.end_s) for c in cues], min_gap=0.05)
    min_gap = float(t.get("min_gap_s", 1.2))
    pad_in = float(t.get("pad_in_s", 0.2))
    pad_out = float(t.get("pad_out_s", 0.3))
    min_window = float(t.get("min_window_s", 1.0))
    for g0, g1 in complement(busy, duration):
        if g1 - g0 < min_gap:
            continue
        start = g0 + pad_in
        end = g1 - pad_out
        if end - start < min_window:
            continue
        cues.append(Cue(0, "DESC", round(start, 3), round(end, 3), round(max(end, g1 - 0.1), 3)))

    cues.sort(key=lambda c: (c.start_s, c.type))
    for i, c in enumerate(cues, 1):
        c.id = i
    return cues


def merge_existing(new: List[Cue], old: List[Cue], tolerance: float = 0.3) -> Tuple[List[Cue], Dict[str, int]]:
    """Rebuild windows but keep everything a person (or Claude) has written."""
    used = set()
    stats = {"kept": 0, "added": 0, "orphaned": 0}

    def compatible(o: Cue, n: Cue) -> bool:  # a DESC window someone turned into TEXT is still the same window
        return o.type == n.type or (o.type in ("DESC", "TEXT") and n.type in ("DESC", "TEXT"))

    for n in new:
        best = None
        for o in old:
            if o.id in used or not compatible(o, n):
                continue
            d = abs(o.start_s - n.start_s)
            if d <= tolerance and (best is None or d < abs(best.start_s - n.start_s)):
                best = o
        if best is None:
            continue
        used.add(best.id)
        n.id = best.id
        if best.type != n.type:
            n.type = best.type
        if best.type != "SUB" and (best.start_s != n.start_s or best.end_s != n.end_s) and best.status in ("approved", "recorded"):
            n.start_s, n.end_s, n.hard_end_s = best.start_s, best.end_s, max(best.hard_end_s, n.hard_end_s)
        edited = best.line.strip() != best.source_text.strip() or best.type != "SUB"
        if best.type == "SUB" and not edited:
            n.line = n.source_text
        else:
            n.line = best.line
        n.status, n.notes, n.clip, n.frame = best.status, best.notes, best.clip, best.frame
        n.measured_s, n.measure = best.measured_s, best.measure
        n.recompute_fit()
        stats["kept"] += 1
    next_id = max([o.id for o in old] + [0]) + 1
    result = list(new)
    for n in result:
        if n.id == 0 or (n.id not in used and any(o.id == n.id for o in old)):
            n.id = next_id
            next_id += 1
            stats["added"] += 1
    for o in old:
        if o.id in used:
            continue
        has_content = o.type != "SUB" and (o.line.strip() or o.status not in ("new",))
        has_content = has_content or (o.type == "SUB" and o.line.strip() != o.source_text.strip())
        if has_content:
            if "orphan" not in o.notes:
                o.notes = (o.notes + "; " if o.notes else "") + "orphan: window changed on rebuild, check timing"
            result.append(o)
            stats["orphaned"] += 1
    result.sort(key=lambda c: (c.start_s, c.id))
    return result, stats


# ---------------------------------------------------------------------------
# The sheet
# ---------------------------------------------------------------------------

class CueSheet:
    def __init__(self, cfg: Config, cues: Optional[List[Cue]] = None):
        self.cfg = cfg
        self.cues: List[Cue] = cues or []
        self.wps = float(cfg.get("timing", "wps", default=2.5))

    @classmethod
    def load(cls, cfg: Config) -> "CueSheet":
        path = cfg.cues_path
        if not path.exists():
            raise SystemExit("no cue sheet yet: run `python ad.py cues build` first")
        return cls(cfg, read_csv(path))

    def save(self) -> Path:
        return write_csv(self.cfg.cues_path, self.cues, self.wps)

    def by_id(self, cid: int) -> Cue:
        for c in self.cues:
            if c.id == cid:
                return c
        raise CueError(f"no cue with id {cid}")

    def next_id(self) -> int:
        return max([c.id for c in self.cues] + [0]) + 1

    def duration_hint(self) -> float:
        return max([c.hard_end_s for c in self.cues] + [0.0])

    def select(self, rng: Optional[str] = None, ids: Optional[str] = None, types: Optional[str] = None,
               statuses: Optional[str] = None, fits: Optional[str] = None) -> List[Cue]:
        out = list(self.cues)
        if rng:
            a, b = parse_range(rng, self.duration_hint())
            out = [c for c in out if c.start_s < (b if b is not None else 1e12) and c.end_s > a]
        if ids:
            want = parse_ids(ids)
            out = [c for c in out if c.id in want]
        if types:
            want_t = {t.strip().upper() for t in types.split(",") if t.strip()}
            out = [c for c in out if c.type in want_t]
        if statuses:
            want_s = {s.strip().lower() for s in statuses.split(",") if s.strip()}
            out = [c for c in out if c.status in want_s]
        if fits:
            want_f = {s.strip().lower() for s in fits.split(",") if s.strip()}
            out = [c for c in out if (c.fits or "unknown") in want_f]
        return out

    # ----- edits --------------------------------------------------------
    def set(self, cid: int, line: Optional[str] = None, status: Optional[str] = None, notes: Optional[str] = None,
            type_: Optional[str] = None, start: Optional[float] = None, end: Optional[float] = None,
            source_text: Optional[str] = None, append_note: bool = False) -> Cue:
        c = self.by_id(cid)
        if type_ is not None:
            type_ = type_.upper()
            if type_ not in TYPES:
                raise CueError(f"type must be one of {TYPES}")
            c.type = type_
        if start is not None or end is not None:
            new_start = c.start_s if start is None else float(start)
            new_end = c.end_s if end is None else float(end)
            if new_end <= new_start:
                raise CueError("end must be after start")
            c.start_s, c.end_s = new_start, new_end
            c.hard_end_s = max(c.hard_end_s, new_end) if end is None else new_end
        if line is not None:
            new_line = " ".join(line.split())
            if new_line != c.line:
                c.line = new_line
                if c.measure == "take":
                    # The recording no longer matches the words: set it aside (the file stays in work/takes)
                    # so builds fall back to the synthetic voice until the line is re-recorded.
                    c.notes = (c.notes + "; " if c.notes else "") + f"line changed after recording; take {c.clip} set aside, re-record"
                    c.clip = ""
                    if status is None and c.status == "recorded":
                        c.status = "drafted"
                c.measured_s, c.measure, c.fits = None, "", ""
            if status is None and c.status == "new":
                c.status = "drafted"
        if status is not None:
            status = status.lower()
            if status not in STATUSES:
                raise CueError(f"status must be one of {STATUSES}")
            c.status = status
        if source_text is not None:
            c.source_text = " ".join(source_text.split())
        if notes is not None:
            c.notes = (c.notes + "; " + notes) if (append_note and c.notes) else notes
        c.recompute_fit()
        return c

    def add(self, type_: str, start: float, end: float, line: str = "", source_text: str = "",
            status: str = "drafted", notes: str = "", hard_end: Optional[float] = None) -> Cue:
        type_ = type_.upper()
        if type_ not in TYPES:
            raise CueError(f"type must be one of {TYPES}")
        if end <= start:
            raise CueError("end must be after start")
        c = Cue(self.next_id(), type_, float(start), float(end), float(hard_end if hard_end else end),
                source_text=" ".join(source_text.split()), line=" ".join(line.split()), status=status, notes=notes)
        self.cues.append(c)
        self.cues.sort(key=lambda x: (x.start_s, x.id))
        return c

    def split(self, cid: int, at: float, gap: float = 0.1) -> Tuple[Cue, Cue]:
        a = self.by_id(cid)
        if not (a.start_s < at < a.end_s):
            raise CueError(f"split point must be inside the window {fmt_short(a.start_s)}-{fmt_short(a.end_s)}")
        b = Cue(self.next_id(), a.type, float(at), a.end_s, a.hard_end_s, status="new",
                notes=f"split from #{a.id}")
        a.end_s = max(a.start_s + 0.2, at - gap)
        a.hard_end_s = max(a.end_s, at - 0.05)
        a.measured_s, a.measure, a.fits = (a.measured_s, a.measure, a.fits) if a.measure == "take" else (None, "", "")
        a.recompute_fit()
        self.cues.append(b)
        self.cues.sort(key=lambda x: (x.start_s, x.id))
        return a, b

    def merge(self, cid: int, cid2: int) -> Cue:
        a, b = self.by_id(cid), self.by_id(cid2)
        if b.start_s < a.start_s:
            a, b = b, a
        a.end_s = max(a.end_s, b.end_s)
        a.hard_end_s = max(a.hard_end_s, b.hard_end_s)
        a.line = " ".join((a.line + " " + b.line).split())
        a.source_text = " ".join((a.source_text + " " + b.source_text).split())
        a.notes = "; ".join(n for n in [a.notes, f"merged #{b.id}", b.notes] if n)
        a.measured_s, a.measure, a.fits = None, "", ""
        self.cues = [c for c in self.cues if c.id != b.id]
        return a

    def remove(self, cid: int) -> None:
        self.by_id(cid)
        self.cues = [c for c in self.cues if c.id != cid]

    def apply(self, ops: List[Dict]) -> List[str]:
        """Apply a list of edits (from a JSON file written by Claude). Returns log lines."""
        log: List[str] = []
        for op in ops:
            if not isinstance(op, dict):
                raise CueError(f"each entry must be an object, got {op!r}")
            if op.get("new"):
                c = self.add(op.get("type", "TEXT"), parse_tc(op["start"]), parse_tc(op["end"]),
                             line=op.get("line", ""), source_text=op.get("source_text", ""),
                             status=op.get("status", "drafted"), notes=op.get("notes", ""))
                log.append(f"added {c.label()}: {c.line[:60]}")
                continue
            if "id" not in op:
                raise CueError(f"entry needs an id or new=true: {op!r}")
            cid = int(op["id"])
            if op.get("remove"):
                self.remove(cid)
                log.append(f"removed #{cid}")
                continue
            if "split_at" in op:
                a, b = self.split(cid, parse_tc(op["split_at"]))
                log.append(f"split #{a.id} -> #{a.id} + #{b.id}")
                continue
            if "merge_with" in op:
                c = self.merge(cid, int(op["merge_with"]))
                log.append(f"merged into #{c.id}")
                continue
            c = self.set(cid, line=op.get("line"), status=op.get("status"), notes=op.get("notes"),
                         type_=op.get("type"),
                         start=parse_tc(op["start"]) if "start" in op else None,
                         end=parse_tc(op["end"]) if "end" in op else None,
                         source_text=op.get("source_text"))
            log.append(f"set {c.label()} [{c.status}]: {c.line[:60]}")
        return log

    # ----- views --------------------------------------------------------
    def table(self, cues: Sequence[Cue], width: int = 72) -> str:
        rows = [f"{'id':>4} {'type':4} {'start':>9} {'win':>5} {'bud':>3} {'meas':>5} {'fit':5} {'status':8} line"]
        for c in cues:
            meas = "" if c.measured_s is None else f"{c.measured_s:.1f}"
            line = c.line if len(c.line) <= width else c.line[:width - 1] + "…"
            rows.append(f"{c.id:>4} {c.type:4} {fmt_short(c.start_s):>9} {c.window_s:>5.1f} {c.budget_words(self.wps):>3} "
                        f"{meas:>5} {c.fits:5} {c.status:8} {line}")
        return "\n".join(rows)

    def summary(self) -> Dict:
        out: Dict = {"total": len(self.cues), "by_type": {}, "by_status": {}, "by_fits": {}}
        for c in self.cues:
            out["by_type"][c.type] = out["by_type"].get(c.type, 0) + 1
            out["by_status"][c.status] = out["by_status"].get(c.status, 0) + 1
            key = c.fits or "unmeasured"
            out["by_fits"][key] = out["by_fits"].get(key, 0) + 1
        desc = [c for c in self.cues if c.type == "DESC"]
        out["desc_seconds"] = round(sum(c.window_s for c in desc), 1)
        out["sub_est_no"] = sum(1 for c in self.cues if c.type == "SUB" and c.est_s(self.wps) > c.window_s)
        return out

    def script_markdown(self, cues: Optional[Sequence[Cue]] = None, title: str = "Audio description script") -> str:
        cues = list(cues if cues is not None else self.cues)
        lines = [f"# {title}", ""]
        current_min = -1
        for c in cues:
            if c.status == "skip":
                continue
            m = int(c.start_s // 60)
            if m != current_min:
                current_min = m
                lines.append(f"\n## {m:02d}:00\n")
            meas = f", {c.measured_s:.1f}s {c.measure}" if c.measured_s is not None else ""
            text = c.line or "(no line yet)"
            lines.append(f"- **{fmt_short(c.start_s)}–{fmt_short(c.end_s)}** `{c.type} #{c.id}` ({c.window_s:.1f}s window{meas}) {text}")
        return "\n".join(lines) + "\n"
