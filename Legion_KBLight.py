#!/usr/bin/env python3
"""Legion Control launcher (kept under the old name so run.sh and existing shortcuts keep working)."""
import logging
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

from legion_control.app import LegionApp, notify_running_instance  # noqa: E402


def main():
    logging.basicConfig(level=logging.INFO if "--verbose" in sys.argv else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if notify_running_instance():
        return  # already running: it has been asked to show its window
    app = LegionApp(APP_DIR)
    if "--hidden" in sys.argv:
        app.withdraw()
    app.mainloop()


if __name__ == "__main__":
    main()
