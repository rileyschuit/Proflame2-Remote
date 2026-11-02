"""Container health check: is the main loop still running? python -m proflame2d.healthcheck"""
import os
import sys
import time

from .config import Config

MAX_AGE_S = 30


def main() -> int:
    path = os.environ.get("PROFLAME2_HEARTBEAT_FILE", Config.heartbeat_file)
    try:
        return 0 if time.time() - os.path.getmtime(path) < MAX_AGE_S else 1
    except OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
