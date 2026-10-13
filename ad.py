#!/usr/bin/env python3
"""Launcher: python ad.py <command>. Re-runs itself inside the project's .venv when one exists."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def _venv_python():
    for rel in (("Scripts", "python.exe"), ("bin", "python")):
        p = os.path.join(ROOT, ".venv", *rel)
        if os.path.exists(p):
            return p
    return None


def _same(a, b):
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except OSError:
        return False


if __name__ == "__main__":
    vp = _venv_python()
    if vp and not _same(sys.executable, vp) and not os.environ.get("AD_NO_VENV"):
        sys.exit(subprocess.call([vp, os.path.abspath(__file__)] + sys.argv[1:]))
    sys.path.insert(0, ROOT)
    from adtool.cli import main
    sys.exit(main())
