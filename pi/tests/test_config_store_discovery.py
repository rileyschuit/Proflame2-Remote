import json

import pytest

from proflame2d.config import ConfigError, load
from proflame2d.discovery import discovery_messages
from proflame2d.frame import State
from proflame2d.store import StateStore

ENV = {
    "PROFLAME2_SERIAL": "A00402",
    "PROFLAME2_ERR1_C": "0",
    "PROFLAME2_ERR1_D": "C",
    "PROFLAME2_ERR2_C": "A",
    "PROFLAME2_ERR2_D": "4",
    "PROFLAME2_MQTT_HOST": "broker",
}


def test_config_loads_with_safe_defaults():
    config = load(ENV)
    assert config.identity.serial == 0xA00402
    assert config.identity.err1_d == 0xC
    assert config.tx_power == "low"
    assert config.base_topic == "home/fireplace"
    assert config.auto_off_minutes == 240


@pytest.mark.parametrize(
    "change",
    [
        {"PROFLAME2_SERIAL": ""},
        {"PROFLAME2_SERIAL": "1000000"},
        {"PROFLAME2_SERIAL": "xyz"},
        {"PROFLAME2_ERR1_C": "10"},
        {"PROFLAME2_MQTT_HOST": ""},
        {"PROFLAME2_TX_POWER": "max"},
    ],
)
def test_config_refuses_bad_values(change):
    with pytest.raises(ConfigError):
        load({**ENV, **change})


def test_store_round_trip(tmp_path, clock):
    store = StateStore(str(tmp_path / "state.json"), clock)
    state = State(power=True, flame=3, fan=2, light=1, front=False, aux=True, pilot=False)
    store.save(state, 100)
    clock.advance(40)
    assert store.load() == (state, pytest.approx(60))


def test_store_with_nothing_saved(tmp_path):
    assert StateStore(str(tmp_path / "state.json")).load() is None


@pytest.mark.parametrize("content", ["not json", "[]", '{"cmd1": 0}', '{"cmd1": 112, "cmd2": 0}'])
def test_store_ignores_a_bad_file(tmp_path, content):
    path = tmp_path / "state.json"
    path.write_text(content)
    assert StateStore(str(path)).load() is None


def test_discovery_covers_the_controls_but_not_the_pilot():
    messages = dict(discovery_messages("homeassistant", "home/fireplace"))
    assert "homeassistant/switch/proflame2_fireplace/power/config" in messages
    assert "homeassistant/number/proflame2_fireplace/flame/config" in messages
    assert not [topic for topic in messages if "pilot" in topic]
    for payload in map(json.loads, messages.values()):
        assert payload["availability_topic"] == "home/fireplace/availability"
        assert payload["state_topic"] == "home/fireplace/state"
    flame = json.loads(messages["homeassistant/number/proflame2_fireplace/flame/config"])
    assert flame["command_template"] == '{"flame": {{ value | int }}}'
    assert flame["max"] == 6
