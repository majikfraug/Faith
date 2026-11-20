"""Automatic time log: how long the whole process takes, without the user keeping a log.

Two sources, merged minute by minute:

  project/timelog.csv  one row per message the user sends to Claude in this folder, per reply Claude finishes, and
                       per session start/end (written by the hook in .claude/hooks/timelog.py), plus notes and manual
                       entries (`ad.py timelog note|add`).
  takes/               the recording files: each one shows when it was recorded and how long it is.

Each minute goes to one phase. Where sources overlap, the stronger one wins:
manual entry > "starting X" ... "done X" note > recording files > watching right after a build > message gaps.
Time between two messages counts only when the gap is short (idle threshold, 30 min by default), except a
reply Claude is still working on and the watch-through after a build, which may run longer.

The report splits the time into the synthetic version (everything up to the note "synthetic done", or up to the
first recording if there is no such note) and the extra work for a recorded voice (everything after).
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .config import Config

LOG_NAME = "timelog.csv"
FIELDS = ["time", "event", "session", "phase", "until", "text"]
AUDIO_EXT = {".wav", ".mp3", ".flac", ".aif", ".aiff", ".m4a", ".ogg"}

PHASES: List[Tuple[str, str]] = [
    ("setup", "Setup: copy files, ingest, cue sheet"),
    ("draft", "Drafting (Claude writes lines)"),
    ("review", "Reviewing and fixing lines"),
    ("build", "Building the review video"),
    ("watching", "Watching or listening through"),
    ("recording", "Recording"),
    ("cleanup", "Cleaning takes"),
    ("mixing", "Mixing in Audition"),
    ("publish", "Final export and YouTube"),
    ("other", "Other (status, saving, questions)"),
]
LABEL = dict(PHASES)
STUDIO_PHASES = {"recording", "cleanup", "mixing"}
MARKER_PHASES = {"watching", "recording", "cleanup", "mixing"}  # work done away from Claude

# First match wins. Tested on the lower-cased message.
RULES: List[Tuple[str, str]] = [
    ("setup", r"/ad-setup|/ad-ingest|/ad-cues|\binstall|\bdoctor\b|\bset ?up\b"),
    ("draft", r"/ad-draft"),
    ("publish", r"/ad-build\s+--final|\bfinal (build|track|export|mix)\b|\bbuild (the )?final|youtube|\bupload|\bpublish"),
    ("build", r"/ad-build"),
    ("recording", r"/ad-place|\brecord|\bre-?takes?\b|\bpick-?ups?\b|\bstudio\b|\bmic\b"),
    ("cleanup", r"\bclean|\bnoise\b|\bplosive|\bclicks?\b|\bde-?ess"),
    ("mixing", r"\baudition\b|\bmix(ing)?\b"),
    ("watching", r"\bwatch|\blisten|review\.mp4|review video"),
    ("review", r"/ad-review|/ad-fit"),
    ("other", r"/ad-status|/ad-help|/ad-time|\btime ?log|save my work|\bcommit\b|\bpush\b"),
]
START_RE = re.compile(r"^\W*(?:ok(?:ay)?\W+)?(?:i'?m\s+|i am\s+|now\s+|about to\s+)?(?:start|starting|begin|beginning|going to)\b")
END_RE = re.compile(r"\b(?:done|finished|stopp?ed|stopping|ending|wrapped up|that'?s it for)\b")
SYNTH_DONE_RE = re.compile(r"synthetic\b.*\b(?:done|finished|complete)|\b(?:done|finished|completed?)\b.*\bsynthetic")
# Free-text messages inherit the current phase, except these move on to reviewing and fixing.
AFTER = {"draft": "review", "build": "review", "watching": "review", "publish": "publish", "other": None}

IDLE_MIN = 30          # a longer gap between messages is a break
REPLY_CAP_MIN = 180    # a reply Claude is working on counts up to this long
MARKER_CAP_MIN = 240   # an unclosed "starting X" counts up to the next message within this window
WATCH_SLACK_MIN = 20   # after a build, a gap up to film length + this counts as watching it


def log_path(cfg: Config) -> Path:
    return cfg.project / LOG_NAME


def now() -> datetime:
    return datetime.now().astimezone()


def classify(text: str) -> Optional[str]:
    t = text.lower()
    for phase, rx in RULES:
        if re.search(rx, t):
            return phase
    return None


def parse_when(value: str, ref: Optional[datetime] = None) -> datetime:
    """'2026-11-20 13:05', '2026-11-20T13:05', or '13:05' (same day as ref, else today). Local time."""
    v = value.strip().replace("T", " ")
    if re.fullmatch(r"\d{1,2}:\d{2}", v):
        base = (ref or now())
        h, m = (int(x) for x in v.split(":"))
        return base.replace(hour=h, minute=m, second=0, microsecond=0)
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        raise ValueError(f"cannot read the time '{value}': use 2026-11-20 13:05 or 13:05")
    return dt if dt.tzinfo else dt.astimezone()


def append(cfg: Config, event: str, text: str = "", phase: str = "", start: Optional[datetime] = None,
           until: Optional[datetime] = None) -> None:
    path = log_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(FIELDS)
        w.writerow([(start or now()).isoformat(timespec="seconds"), event, "adtool", phase,
                    until.isoformat(timespec="seconds") if until else "", " ".join(text.split())[:160]])


# ---------------------------------------------------------------------------
# reading the sources
# ---------------------------------------------------------------------------

@dataclass
class Event:
    t: datetime
    kind: str          # start | prompt | stop | end | note | manual
    text: str = ""
    phase: str = ""
    until: Optional[datetime] = None


def read_events(path: Path) -> List[Event]:
    if not path.exists():
        return []
    out: List[Event] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                t = parse_when(row.get("time") or "")
                until = parse_when(row["until"]) if row.get("until") else None
            except ValueError:
                continue
            out.append(Event(t, (row.get("event") or "").strip(), row.get("text") or "", (row.get("phase") or "").strip(), until))
    out.sort(key=lambda e: e.t)
    return out


@dataclass
class Take:
    path: Path
    phase: str         # recording | cleanup
    start: datetime
    end: datetime
    seconds: float


def _audio_seconds(path: Path) -> float:
    try:
        import soundfile as sf
        return float(sf.info(str(path)).duration)
    except Exception:
        return 0.0


def read_takes(cfg: Config) -> List[Take]:
    root = cfg.dir("takes")
    if not root.exists():
        return []
    out: List[Take] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in AUDIO_EXT:
            continue
        rel_parts = [x.lower() for x in p.relative_to(root).parts[:-1]]
        if any(x.endswith("_split") for x in rel_parts):
            continue  # made by the toolkit, not by the narrator
        phase = "cleanup" if any(x.startswith("clean") for x in rel_parts) else "recording"
        st = p.stat()
        secs = _audio_seconds(p)
        end = datetime.fromtimestamp(st.st_mtime).astimezone()
        born = datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_ctime)).astimezone()
        start = end - timedelta(seconds=secs)
        # Recorded straight into this folder: the file was created when recording began. Copied in later: the
        # creation time is the copy time (after the end), so the length is all we know.
        if born < start and (end - born) <= timedelta(hours=4):
            start = born
        out.append(Take(p, phase, start, end, secs))
    return out


def film_minutes(cfg: Config) -> Optional[float]:
    p = cfg.work / "media.json"
    try:
        return float(json.loads(p.read_text(encoding="utf-8"))["duration"]) / 60.0
    except Exception:
        return None


# ---------------------------------------------------------------------------
# minute-by-minute timeline
# ---------------------------------------------------------------------------

def _minutes(a: datetime, b: datetime) -> Iterable[int]:
    lo = int(a.timestamp() // 60)
    hi = max(lo + 1, int(math.ceil(b.timestamp() / 60)))
    return range(lo, hi)


class Timeline:
    def __init__(self) -> None:
        self.cells: Dict[int, Tuple[int, str, str]] = {}   # minute -> (priority, phase, source)
        self.busy: set = set()                              # minutes Claude was working on a reply

    def paint(self, a: datetime, b: datetime, phase: str, priority: int, source: str) -> None:
        if b <= a:
            b = a + timedelta(seconds=1)
        for m in _minutes(a, b):
            cur = self.cells.get(m)
            if cur is None or priority > cur[0]:
                self.cells[m] = (priority, phase, source)


@dataclass
class Result:
    timeline: Timeline
    split_minute: Optional[int]
    split_reason: str
    flags: List[str]
    takes: List[Take]
    events: List[Event]
    film_min: Optional[float]
    idle_min: int


def analyse(cfg: Config, idle_min: int = IDLE_MIN, events: Optional[List[Event]] = None,
            takes: Optional[List[Take]] = None, film_min: Optional[float] = None) -> Result:
    events = read_events(log_path(cfg)) if events is None else events
    takes = read_takes(cfg) if takes is None else takes
    film_min = film_minutes(cfg) if film_min is None else film_min
    tl = Timeline()
    flags: List[str] = []
    idle = timedelta(minutes=idle_min)
    watch_gap = timedelta(minutes=(film_min or 70) + WATCH_SLACK_MIN)

    # 1. message gaps (priority 1) and the watch-through after a build (priority 2)
    stream = [e for e in events if e.kind in ("start", "prompt", "stop", "end", "note")]
    phase = "setup"
    last_prompt_phase = "setup"
    waiting = False          # a prompt has been sent and Claude has not finished replying
    for i, e in enumerate(stream):
        nxt = stream[i + 1] if i + 1 < len(stream) else None
        if e.kind in ("prompt", "note"):
            got = classify(e.text)
            if got is None:
                got = AFTER.get(phase, phase) or last_prompt_phase
            if got != "other":
                last_prompt_phase = got
            phase = got
            waiting = e.kind == "prompt"
        interval_phase, priority, limit = phase, 1, idle
        if e.kind == "stop":
            waiting = False
            if phase in ("build", "publish"):
                interval_phase, priority, limit = "watching", 2, watch_gap
                phase = "watching"
        if nxt is None:
            tl.paint(e.t, e.t, interval_phase, priority, "messages")
            continue
        gap = nxt.t - e.t
        if waiting and nxt.kind == "stop" and gap <= timedelta(minutes=REPLY_CAP_MIN):
            tl.paint(e.t, nxt.t, interval_phase, 1, "messages")
            for m in _minutes(e.t, nxt.t):
                tl.busy.add(m)
        elif gap <= limit:
            tl.paint(e.t, nxt.t, interval_phase, priority if gap > idle else 1, "watch-assumed" if gap > idle else "messages")
        else:
            tl.paint(e.t, e.t, interval_phase, 1, "messages")
        if e.kind == "end":
            waiting = False

    # 2. recording files (priority 3): files less than the idle threshold apart form one session
    for kind in ("recording", "cleanup"):
        spans = sorted((t.start, t.end) for t in takes if t.phase == kind)
        cur: Optional[List[datetime]] = None
        for a, b in spans:
            if cur and a - cur[1] <= idle:
                cur[1] = max(cur[1], b)
                continue
            if cur:
                tl.paint(cur[0], cur[1], kind, 3, "files")
            cur = [a, b]
        if cur:
            tl.paint(cur[0], cur[1], kind, 3, "files")

    # 3. "starting X" ... "done X" in messages or notes (priority 4)
    talk = [e for e in events if e.kind in ("prompt", "note")]
    all_times = sorted([e.t for e in events if e.kind in ("prompt", "note", "start")])
    for i, e in enumerate(talk):
        low = e.text.lower()
        p = classify(e.text)
        if not START_RE.search(low) or p not in MARKER_PHASES:
            continue
        end_t: Optional[datetime] = None
        for later in talk[i + 1:]:
            ll = later.text.lower()
            if END_RE.search(ll):
                end_t = later.t
                break
            if START_RE.search(ll) and classify(later.text) in MARKER_PHASES:
                end_t = later.t
                break
        cap = e.t + timedelta(minutes=MARKER_CAP_MIN)
        if end_t is not None and end_t - e.t > timedelta(hours=12):
            end_t = None
        if end_t is None:
            nxt_t = next((t for t in all_times if t > e.t), None)
            file_ends = [t.end for t in takes if e.t <= t.start <= cap]
            if nxt_t is not None and nxt_t <= cap:
                end_t = nxt_t
            elif file_ends:
                end_t = max(file_ends)
            if end_t is None:
                flags.append(f"\"{e.text[:60]}\" at {e.t:%Y-%m-%d %H:%M} has no matching \"done\"; nothing counted for it. "
                              f"Add the time with `python ad.py timelog add --phase {p} --start ... --end ...`.")
                continue
            flags.append(f"\"{e.text[:60]}\" at {e.t:%Y-%m-%d %H:%M} had no \"done\"; counted until {end_t:%H:%M}.")
        tl.paint(e.t, end_t, p, 4, "your note")

    # 4. manual entries (priority 5)
    for e in events:
        if e.kind == "manual" and e.until is not None and e.phase:
            tl.paint(e.t, e.until, e.phase if e.phase in LABEL else "other", 5, "manual")

    # where the synthetic version ends
    split_minute: Optional[int] = None
    split_reason = ""
    for e in events:
        if e.kind in ("prompt", "note") and SYNTH_DONE_RE.search(e.text.lower()):
            split_minute = int(e.t.timestamp() // 60) + 1
            split_reason = f"your note \"{e.text[:60]}\" ({e.t:%Y-%m-%d %H:%M})"
            break
    if split_minute is None:
        studio = sorted(m for m, (_, ph, _) in tl.cells.items() if ph in STUDIO_PHASES)
        if studio:
            split_minute = studio[0]
            split_reason = f"the first recording ({datetime.fromtimestamp(split_minute * 60).astimezone():%Y-%m-%d %H:%M}); say \"synthetic done\" to mark it exactly"
    return Result(tl, split_minute, split_reason, flags, takes, events, film_min, idle_min)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def hm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60}:{m % 60:02d}"


def sessions(tl: Timeline, idle_min: int) -> List[Tuple[int, int, int, Counter]]:
    """(first minute, last minute, active minutes, phase counter) for runs of activity."""
    out: List[Tuple[int, int, int, Counter]] = []
    for m in sorted(tl.cells):
        ph = tl.cells[m][1]
        if out and m - out[-1][1] <= idle_min:
            a, _, n, c = out[-1]
            c[ph] += 1
            out[-1] = (a, m, n + 1, c)
        else:
            out.append((m, m, 1, Counter({ph: 1})))
    return out


def report(cfg: Config, res: Result) -> str:
    tl = res.timeline
    split = res.split_minute
    a: Counter = Counter()
    b: Counter = Counter()
    for m, (_, ph, _) in tl.cells.items():
        (b if split is not None and m >= split else a)[ph] += 1
    total_a, total_b = sum(a.values()), sum(b.values())
    assumed = sum(1 for _, _, src in tl.cells.values() if src == "watch-assumed")
    prompts = sum(1 for e in res.events if e.kind == "prompt")
    sess = sessions(tl, res.idle_min)
    name = cfg.get("project_name", default="") or "this film"

    L = [f"# Time log: {name}", "",
         f"Made {now():%Y-%m-%d %H:%M} from {prompts} messages to Claude, {len(res.takes)} recording file(s) "
         f"and {sum(1 for e in res.events if e.kind in ('note', 'manual'))} note(s). "
         f"A gap of more than {res.idle_min} minutes between messages counts as a break.", ""]
    if not res.events:
        L += ["**Nothing logged yet.** The hook in `.claude/hooks/timelog.py` writes `project/timelog.csv` each time you",
              "send a message in this folder. If this stays empty, check `/hooks` in Claude Code.", ""]
    L += ["## Totals (hours:minutes)", "",
          "| Phase | Synthetic version | Extra for recorded voice | Recorded voice, whole process |",
          "|---|---|---|---|"]
    for key, label in PHASES:
        if a[key] or b[key]:
            L.append(f"| {label} | {hm(a[key])} | {hm(b[key])} | {hm(a[key] + b[key])} |")
    L.append(f"| **Total** | **{hm(total_a)}** | **{hm(total_b)}** | **{hm(total_a + total_b)}** |")
    L.append("")
    if res.film_min:
        fm = res.film_min
        L.append(f"Film length {fm:.1f} min. Work minutes per film minute: synthetic {total_a / fm:.1f}, "
                 f"recorded voice {(total_a + total_b) / fm:.1f}.")
    L.append(f"Of all this, Claude was busy replying for {hm(len(tl.busy))} (time you may have spent waiting).")
    if split is not None:
        L.append(f"The synthetic version ends at {res.split_reason}.")
    else:
        L.append("No recording yet, so everything so far counts toward the synthetic version.")
    L.append("")

    rec = [t for t in res.takes if t.phase == "recording"]
    if rec:
        mic = sum(t.seconds for t in rec) / 60.0
        ids = Counter(m.group(1) for t in rec if (m := re.match(r"(\d{3,5})", t.path.stem)))
        retakes = sum(n - 1 for n in ids.values() if n > 1)
        L += ["## Recording", "",
              f"- {len(rec)} recording file(s), {mic:.1f} min of audio in total.",
              f"- Cleaned files (in a `clean` folder): {sum(1 for t in res.takes if t.phase == 'cleanup')}.",
              f"- Lines recorded more than once (by cue number in the file name): {sum(1 for n in ids.values() if n > 1)} "
              f"({retakes} extra take(s))." if ids else "- Files are not named by cue number, so retakes are not counted.",
              ""]

    if sess:
        L += ["## Work sessions", "", "| Date | From | To | Counted | Mostly |", "|---|---|---|---|---|"]
        for first, last, n, c in sess:
            t0 = datetime.fromtimestamp(first * 60).astimezone()
            t1 = datetime.fromtimestamp((last + 1) * 60).astimezone()
            top = ", ".join(LABEL.get(k, k).split(" (")[0].split(":")[0] for k, _ in c.most_common(3))
            L.append(f"| {t0:%a %Y-%m-%d} | {t0:%H:%M} | {t1:%H:%M} | {hm(n)} | {top} |")
        L.append("")

    checks = list(res.flags)
    if assumed:
        checks.append(f"{hm(assumed)} after a build was counted as watching the review video, because the next message "
                      f"came within the film's length. If you did something else, say so and it can be corrected.")
    if checks:
        L += ["## Please check", ""] + [f"- {c}" for c in checks] + [""]
    L += ["Add anything done without a message (a studio session, mixing on another computer):",
          "`python ad.py timelog add --phase recording --start \"2026-11-20 13:00\" --end \"15:10\"`.",
          "Phases: " + ", ".join(k for k, _ in PHASES) + "."]
    return "\n".join(L) + "\n"
