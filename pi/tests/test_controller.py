import pytest
from conftest import TEST_IDENTITY

from proflame2d.controller import CommandError, Controller, apply_fields
from proflame2d.frame import State, build_payload, encode_burst


class Radio:
    def __init__(self):
        self.sent = []
        self.ok = True

    def __call__(self, burst):
        self.sent.append(burst)
        return self.ok


def burst_for(state):
    return encode_burst(build_payload(TEST_IDENTITY, state))


@pytest.fixture
def radio():
    return Radio()


@pytest.fixture
def controller(radio, clock):
    return Controller(TEST_IDENTITY, radio, clock, auto_off_minutes=10)


def run(controller, clock, seconds, step=0.25):
    for _ in range(int(seconds / step)):
        controller.tick()
        clock.advance(step)


def test_nothing_is_sent_until_a_command_arrives(controller, radio, clock):
    run(controller, clock, 5)
    assert radio.sent == []


def test_commit_sends_the_new_state_once(controller, radio, clock):
    next_state = apply_fields(controller.state, {"power": True, "flame": 3})
    controller.commit(next_state)
    run(controller, clock, 5)
    assert radio.sent == [burst_for(next_state)]


def test_sends_are_spaced_out_and_the_latest_state_wins(controller, radio, clock):
    controller.commit(apply_fields(controller.state, {"flame": 2}))
    controller.tick()
    controller.commit(apply_fields(controller.state, {"flame": 3}))
    controller.commit(apply_fields(controller.state, {"flame": 4}))
    controller.tick()
    assert len(radio.sent) == 1
    clock.advance(0.5)
    controller.tick()
    assert radio.sent[-1] == burst_for(controller.state)
    assert controller.state.flame == 4


def test_auto_off_turns_it_off_and_repeats_the_frame(controller, radio, clock):
    controller.commit(apply_fields(controller.state, {"power": True}))
    run(controller, clock, 599)
    assert controller.state.power is True
    assert len(radio.sent) == 1
    run(controller, clock, 10)
    assert controller.state.power is False
    assert radio.sent[1:] == [burst_for(controller.state)] * 3


def test_changing_levels_does_not_extend_the_timer(controller, clock):
    controller.commit(apply_fields(controller.state, {"power": True}))
    run(controller, clock, 300)
    controller.commit(apply_fields(controller.state, {"flame": 5}))
    assert controller.remaining_s() == pytest.approx(300, abs=1)


def test_a_refused_off_keeps_retrying_until_it_goes_out(controller, radio, clock):
    controller.commit(apply_fields(controller.state, {"power": True}))
    run(controller, clock, 1)
    radio.ok = False
    controller.off()
    run(controller, clock, 7)
    attempts = len(radio.sent)
    assert attempts >= 3
    assert controller.pending is True
    radio.ok = True
    run(controller, clock, 3)
    assert controller.pending is False
    run(controller, clock, 10)
    assert len(radio.sent) == attempts + 1


def test_restore_does_not_transmit(controller, radio, clock):
    controller.restore(State(power=True, flame=3), remaining_s=100)
    run(controller, clock, 50)
    assert radio.sent == []
    assert controller.remaining_s() == pytest.approx(50, abs=1)


def test_restore_with_the_timer_expired_sends_off(controller, radio, clock):
    controller.restore(State(power=True, flame=3), remaining_s=-5)
    run(controller, clock, 6)
    assert controller.state.power is False
    assert radio.sent[0] == burst_for(State(power=False, flame=3))


def test_restore_caps_the_timer_at_one_full_timer(controller):
    controller.restore(State(power=True), remaining_s=999999)
    assert controller.remaining_s() == pytest.approx(600)


def test_restore_when_off_has_no_timer(controller):
    controller.restore(State(power=False), remaining_s=None)
    assert controller.remaining_s() == 0


@pytest.mark.parametrize(
    "fields",
    [
        {},
        [],
        "power",
        {"flame": 7},
        {"flame": -1},
        {"flame": True},
        {"flame": "3"},
        {"flame": 2.5},
        {"power": 2},
        {"power": "on"},
        {"thermostat": True},
        {"flame": 3, "nope": 1},
    ],
)
def test_bad_commands_are_refused_without_changing_anything(fields):
    with pytest.raises(CommandError):
        apply_fields(State(), fields)


def test_switches_accept_booleans_and_zero_or_one():
    assert apply_fields(State(), {"power": 1}).power is True
    assert apply_fields(State(power=True), {"power": False}).power is False


@pytest.mark.parametrize("minutes", [0, 721])
def test_auto_off_has_limits(radio, clock, minutes):
    with pytest.raises(ValueError):
        Controller(TEST_IDENTITY, radio, clock, auto_off_minutes=minutes)
