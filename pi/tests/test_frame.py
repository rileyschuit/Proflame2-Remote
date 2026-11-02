import os
import subprocess

import pytest
from conftest import TEST_IDENTITY

from proflame2d.frame import (
    BURST_BYTES,
    State,
    build_payload,
    cmd1_byte,
    cmd2_byte,
    encode_burst,
    err_byte,
    state_from_command_bytes,
)

# (cmd1, cmd2, err1, err2): the distinct frames captured from the real remote on 11-02.
CAPTURED = [(128, 166, 132, 136), (129, 166, 165, 136), (129, 38, 165, 0)]


@pytest.mark.parametrize("cmd1,cmd2,err1,err2", CAPTURED)
def test_checksums_match_the_real_remote(cmd1, cmd2, err1, err2):
    assert err_byte(cmd1, TEST_IDENTITY.err1_c, TEST_IDENTITY.err1_d) == err1
    assert err_byte(cmd2, TEST_IDENTITY.err2_c, TEST_IDENTITY.err2_d) == err2


def test_payload_layout_matches_a_captured_frame():
    state = State(pilot=True, power=False, front=True, fan=2, flame=6)
    assert build_payload(TEST_IDENTITY, state) == bytes((0xA0, 0x04, 0x02, 128, 166, 132, 136))


@pytest.mark.parametrize("cmd1,cmd2", [(128, 166), (129, 38), (0x61, 0x0E), (0x01, 0xE6)])
def test_command_bytes_round_trip(cmd1, cmd2):
    state = state_from_command_bytes(cmd1, cmd2)
    assert (cmd1_byte(state), cmd2_byte(state)) == (cmd1, cmd2)


def test_thermostat_bit_is_never_set_or_restored():
    state = state_from_command_bytes(0x83, 0x00)
    assert cmd1_byte(state) == 0x81


@pytest.mark.parametrize("cmd1,cmd2", [(0x70, 0), (0, 0x70), (0, 0x07)])
def test_out_of_range_levels_are_refused(cmd1, cmd2):
    with pytest.raises(ValueError):
        state_from_command_bytes(cmd1, cmd2)


def test_burst_has_the_right_length():
    assert len(encode_burst(build_payload(TEST_IDENTITY, State()))) == BURST_BYTES


GEN_BURST = os.environ.get("GEN_BURST")


@pytest.mark.skipif(not GEN_BURST, reason="set GEN_BURST to tests/bin/gen_burst (make pi-test)")
def test_python_and_cpp_encoders_produce_the_same_bytes():
    identity = TEST_IDENTITY
    count = 0
    for pilot in (0, 1):
        for level in range(7):
            for power in (0, 1):
                cmd1 = pilot << 7 | level << 4 | power
                for cmd2 in (level, level << 4, 0x80 | level, 0x08 | level):
                    expected = subprocess.run(
                        [GEN_BURST, hex(identity.serial), str(cmd1), str(cmd2),
                         str(identity.err1_c), str(identity.err1_d),
                         str(identity.err2_c), str(identity.err2_d)],
                        check=True, capture_output=True, text=True,
                    ).stdout.strip()
                    state = state_from_command_bytes(cmd1, cmd2)
                    assert encode_burst(build_payload(identity, state)).hex() == expected
                    count += 1
    assert count == 112
