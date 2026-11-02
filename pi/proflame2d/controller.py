"""Fireplace state, command handling and the auto-off timer.

Python port of libraries/Proflame2/src/Proflame2Controller.cpp. The radio and clock come
in from the caller, so tests can run it without hardware.
"""
from dataclasses import replace
from typing import Callable

from .frame import MAX_LEVEL, Identity, State, build_payload, encode_burst

DEFAULT_AUTO_OFF_MINUTES = 240
MAX_AUTO_OFF_MINUTES = 720

_MIN_SEND_GAP_S = 0.5  # a burst is on air for about 400 ms
_OFF_RESEND_GAP_S = 2.0
_OFF_RESENDS = 2  # there is no ACK path yet, so repeat a timed off

_LEVELS = ("flame", "fan", "light")
_SWITCHES = ("power", "front", "aux", "pilot")


class CommandError(ValueError):
    """A command was refused. The message is safe to publish."""


def apply_fields(state: State, fields: object) -> State:
    """Returns the state with all fields applied, or raises without applying any."""
    if not isinstance(fields, dict) or not fields:
        raise CommandError("expected a JSON object")
    changes = {}
    for name, value in fields.items():
        if name in _LEVELS:
            if isinstance(value, bool) or not isinstance(value, int):
                raise CommandError(f"{name} must be an integer")
            if not 0 <= value <= MAX_LEVEL:
                raise CommandError(f"{name} must be 0-{MAX_LEVEL}")
        elif name in _SWITCHES:
            if not isinstance(value, bool) and value not in (0, 1):
                raise CommandError(f"{name} must be true or false")
            value = bool(value)
        else:
            raise CommandError(f"unknown field: {name}")
        changes[name] = value
    return replace(state, **changes)


class Controller:
    def __init__(
        self,
        identity: Identity,
        transmit: Callable[[bytes], bool],
        clock: Callable[[], float],
        auto_off_minutes: int = DEFAULT_AUTO_OFF_MINUTES,
    ):
        if not 1 <= auto_off_minutes <= MAX_AUTO_OFF_MINUTES:
            raise ValueError(f"auto-off must be 1-{MAX_AUTO_OFF_MINUTES} minutes")
        self._identity = identity
        self._transmit = transmit
        self._clock = clock
        self._auto_off_s = auto_off_minutes * 60.0
        self.auto_off_minutes = auto_off_minutes
        self.state = State()
        self._deadline: float | None = None
        self._dirty = False
        self._sent_once = False
        self._last_send = 0.0
        self._off_resends = 0
        self.last_transmit_ok = True

    def restore(self, state: State, remaining_s: float | None) -> None:
        """Restores saved state without transmitting.

        A fireplace that was on keeps what was left of its timer, never more than a full
        one. With nothing left, the next tick() turns it off.
        """
        self.state = state
        if state.power:
            left = self._auto_off_s if remaining_s is None else remaining_s
            self._deadline = self._clock() + max(0.0, min(left, self._auto_off_s))

    def commit(self, next_state: State) -> None:
        """Takes a validated state. tick() sends it."""
        if next_state.power and not self.state.power:
            self._deadline = self._clock() + self._auto_off_s
        if not next_state.power:
            self._deadline = None
        if not (self.state.power and not next_state.power):
            self._off_resends = 0
        self.state = next_state
        self._dirty = True

    def off(self) -> None:
        self.commit(replace(self.state, power=False))

    def off_with_resends(self) -> None:
        """An off nobody is around to check: send it more than once."""
        self.off()
        self._off_resends = _OFF_RESENDS

    def remaining_s(self) -> float:
        if self._deadline is None:
            return 0.0
        return max(0.0, self._deadline - self._clock())

    @property
    def pending(self) -> bool:
        return self._dirty or self._off_resends > 0

    def tick(self) -> bool:
        """Call often. Sends pending frames and enforces the timer. True if it tried to send."""
        if self._deadline is not None and self.remaining_s() == 0.0:
            self.off_with_resends()

        now = self._clock()
        since_send = now - self._last_send
        if self._dirty and (not self._sent_once or since_send >= _MIN_SEND_GAP_S):
            self._dirty = False
            self._send(now)
            return True
        if self._off_resends > 0 and not self.state.power and since_send >= _OFF_RESEND_GAP_S:
            self._off_resends -= 1
            self._send(now)
            return True
        return False

    def _send(self, now: float) -> None:
        burst = encode_burst(build_payload(self._identity, self.state))
        self.last_transmit_ok = self._transmit(burst)
        self._last_send = now
        self._sent_once = True
        # The radio refused an off frame: keep trying, tick() paces the retries.
        if not self.last_transmit_ok and not self.state.power and self._off_resends == 0:
            self._off_resends = 1
