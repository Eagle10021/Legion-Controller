#!/usr/bin/env python3
"""
Claude Code hook: reports a session as waiting (on) or answered (off) to Legion Control.

Usage: attention_hook.py on|off, with the hook's JSON on stdin. Always exits 0, so a stopped app never affects Claude.
"""
import json
import subprocess
import sys

SERVICE = "org.legioncontrol.Attention"
PATH = "/org/legioncontrol/Attention"


def main():
    try:
        session = json.load(sys.stdin).get("session_id") or "default"
    except (ValueError, AttributeError):
        session = "default"
    waiting = "true" if sys.argv[1:] == ["on"] else "false"
    try:
        subprocess.run(["gdbus", "call", "--session", "--dest", SERVICE, "--object-path", PATH,
                        "--method", f"{SERVICE}.Set", f"claude:{session}", waiting],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


if __name__ == "__main__":
    main()
