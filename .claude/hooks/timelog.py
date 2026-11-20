#!/usr/bin/env python3
"""Claude Code hook: add one row to project/timelog.csv when a session starts or ends, when the user sends a
message, and when Claude finishes replying. `python ad.py timelog` turns these rows into hours per phase.

Standard library only (it runs before the project's .venv exists). It never prints, because a prompt hook's
output is shown to Claude, and it never fails, so a logging problem can never block a message.
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

FIELDS = ["time", "event", "session", "phase", "until", "text"]
EVENTS = {"SessionStart": "start", "UserPromptSubmit": "prompt", "Stop": "stop", "SessionEnd": "end"}


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        data = {}
    name = str(data.get("hook_event_name") or "")
    event = EVENTS.get(name, name.lower() or "event")
    text = " ".join(str(data.get("prompt") or "").split())[:160]
    log = Path(__file__).resolve().parents[2] / "project" / "timelog.csv"
    log.parent.mkdir(parents=True, exist_ok=True)
    new = not log.exists() or log.stat().st_size == 0
    with open(log, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(FIELDS)
        w.writerow([datetime.now().astimezone().isoformat(timespec="seconds"), event,
                    str(data.get("session_id") or "")[:8], "", "", text])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
