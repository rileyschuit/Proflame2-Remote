"""Saves state across restarts, so a restart can't forget a fire that's burning."""
import json
import logging
import os
import time
from typing import Callable

from .frame import State, cmd1_byte, cmd2_byte, state_from_command_bytes

log = logging.getLogger(__name__)


class StateStore:
    def __init__(self, path: str, wall_clock: Callable[[], float] = time.time):
        self._path = path
        self._wall_clock = wall_clock

    def save(self, state: State, remaining_s: float) -> None:
        record = {
            "cmd1": cmd1_byte(state),
            "cmd2": cmd2_byte(state),
            "autoOffAt": self._wall_clock() + remaining_s if state.power else None,
        }
        temporary = self._path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self._path)

    def load(self) -> tuple[State, float | None] | None:
        """Returns (state, seconds left on the timer), or None if nothing usable is saved.

        The timer is saved as a wall-clock time so that crash loops can't keep extending
        it. If the clock jumped forward the fire goes out early, which is the safe side,
        and the controller caps a backward jump at one full timer.
        """
        try:
            with open(self._path, encoding="utf-8") as handle:
                record = json.load(handle)
            state = state_from_command_bytes(int(record["cmd1"]), int(record["cmd2"]))
            auto_off_at = record.get("autoOffAt")
            remaining = None if auto_off_at is None else float(auto_off_at) - self._wall_clock()
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            log.warning("ignoring unreadable state file: %s", error)
            return None
        return state, remaining
