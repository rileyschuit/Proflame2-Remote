"""End to end against a real Mosquitto, with a fake radio."""
import json
import os
import shutil
import socket
import subprocess
import threading
import time

import paho.mqtt.client as mqtt
import pytest
from conftest import TEST_IDENTITY

from proflame2d.config import Config
from proflame2d.frame import State, build_payload, encode_burst
from proflame2d.service import Service
from proflame2d.store import StateStore

MOSQUITTO = os.environ.get("MOSQUITTO") or shutil.which("mosquitto")
pytestmark = pytest.mark.skipif(not MOSQUITTO, reason="needs a mosquitto binary")

BASE = "home/fireplace"


class FakeRadio:
    def __init__(self, present=True):
        self.will_be_present = present
        self.present = False
        self.version = 0x14
        self.sent = []

    def begin(self, _frequency_khz, _power):
        self.present = self.will_be_present
        return self.present

    def transmit(self, burst):
        self.sent.append(burst)
        return self.present


def burst_for(state):
    return encode_burst(build_payload(TEST_IDENTITY, state))


def wait_for(condition, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def broker(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    conf = tmp_path / "mosquitto.conf"
    conf.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\n")
    process = subprocess.Popen([MOSQUITTO, "-c", str(conf)], stderr=subprocess.DEVNULL)
    def is_up():
        with socket.socket() as sock:
            return sock.connect_ex(("127.0.0.1", port)) == 0
    assert wait_for(is_up)
    yield port
    process.terminate()
    process.wait()


class Watcher:
    def __init__(self, port):
        self.messages = {}
        self.errors = []
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_message = self._on_message
        self.client.connect("127.0.0.1", port)
        self.client.subscribe("#")
        self.client.loop_start()

    def _on_message(self, _client, _userdata, message):
        self.messages[message.topic] = message.payload.decode()
        if message.topic == f"{BASE}/error":
            self.errors.append(message.payload.decode())

    def state(self):
        raw = self.messages.get(f"{BASE}/state")
        return json.loads(raw) if raw else {}

    def publish(self, topic, payload, retain=False):
        self.client.publish(topic, payload, qos=1, retain=retain).wait_for_publish(2)

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


@pytest.fixture
def watcher(broker):
    watcher = Watcher(broker)
    yield watcher
    watcher.close()


class Running:
    def __init__(self, port, tmp_path, radio, auto_off_minutes=240):
        config = Config(
            identity=TEST_IDENTITY,
            mqtt_host="127.0.0.1",
            mqtt_port=port,
            auto_off_minutes=auto_off_minutes,
            state_file=str(tmp_path / "state.json"),
            heartbeat_file=str(tmp_path / "heartbeat"),
        )
        self.radio = radio
        self.service = Service(config, radio)
        self.thread = threading.Thread(target=self.service.run)
        self.thread.start()

    def stop(self):
        self.service.stop()
        self.thread.join(timeout=15)
        assert not self.thread.is_alive()


@pytest.fixture
def start(broker, tmp_path):
    running = []

    def _start(radio=None, **kwargs):
        service = Running(broker, tmp_path, radio or FakeRadio(), **kwargs)
        running.append(service)
        return service

    yield _start
    for service in running:
        if service.thread.is_alive():
            service.stop()


def test_announces_itself_to_home_assistant(start, watcher):
    start()
    assert wait_for(lambda: watcher.messages.get(f"{BASE}/availability") == "online")
    assert "homeassistant/switch/proflame2_fireplace/power/config" in watcher.messages
    assert wait_for(lambda: watcher.state().get("assumed") is True)


def test_sends_nothing_at_startup(start, watcher):
    service = start()
    assert wait_for(lambda: watcher.state())
    time.sleep(0.3)
    assert service.radio.sent == []


def test_set_transmits_the_frame_and_updates_state(start, watcher):
    service = start()
    assert wait_for(lambda: watcher.messages.get(f"{BASE}/availability") == "online")
    watcher.publish(f"{BASE}/set", '{"power": true, "flame": 3}')
    expected = burst_for(State(power=True, flame=3))
    assert wait_for(lambda: service.radio.sent == [expected])
    assert wait_for(lambda: watcher.state().get("power") is True)
    assert watcher.state()["flame"] == 3
    assert watcher.state()["autoOffRemainingS"] > 0


def test_retained_commands_are_refused_so_a_broker_cannot_relight_it(start, watcher):
    watcher.publish(f"{BASE}/set", '{"power": true}', retain=True)
    service = start()
    assert wait_for(lambda: "retained commands are refused" in watcher.errors)
    assert service.radio.sent == []
    watcher.publish(f"{BASE}/set", "", retain=True)


@pytest.mark.parametrize("payload", ["not json", '{"flame": 9}', '{"thermostat": true}', "x" * 300])
def test_bad_commands_publish_an_error(start, watcher, payload):
    service = start()
    assert wait_for(lambda: watcher.messages.get(f"{BASE}/availability") == "online")
    watcher.publish(f"{BASE}/set", payload)
    assert wait_for(lambda: watcher.errors)
    assert service.radio.sent == []


def test_stopping_with_the_fire_on_turns_it_off_first(start, watcher, tmp_path):
    service = start()
    assert wait_for(lambda: watcher.messages.get(f"{BASE}/availability") == "online")
    watcher.publish(f"{BASE}/set", '{"power": true}')
    assert wait_for(lambda: service.radio.sent)
    service.stop()
    off = burst_for(State(power=False))
    assert service.radio.sent[-1] == off
    assert service.radio.sent.count(off) == 3
    assert wait_for(lambda: watcher.messages.get(f"{BASE}/availability") == "offline")
    assert wait_for(lambda: watcher.state().get("power") is False)
    saved, _ = StateStore(str(tmp_path / "state.json")).load()
    assert saved.power is False


def test_stopping_with_the_fire_off_sends_nothing(start, watcher):
    service = start()
    assert wait_for(lambda: watcher.messages.get(f"{BASE}/availability") == "online")
    service.stop()
    assert service.radio.sent == []


def test_restart_keeps_the_timer_and_sends_nothing(start, watcher, tmp_path):
    StateStore(str(tmp_path / "state.json")).save(State(power=True, flame=4), 100)
    service = start()
    assert wait_for(lambda: watcher.state().get("flame") == 4)
    assert 90 <= watcher.state()["autoOffRemainingS"] <= 100
    assert service.radio.sent == []


def test_restart_after_the_timer_ran_out_turns_it_off(start, watcher, tmp_path):
    StateStore(str(tmp_path / "state.json")).save(State(power=True, flame=4), -60)
    service = start()
    off = burst_for(State(power=False, flame=4))
    assert wait_for(lambda: service.radio.sent and service.radio.sent[0] == off)
    assert wait_for(lambda: watcher.state().get("power") is False)


def test_without_a_radio_it_refuses_on_but_accepts_off(start, watcher, tmp_path):
    StateStore(str(tmp_path / "state.json")).save(State(power=False), 0)
    service = start(FakeRadio(present=False))
    assert wait_for(lambda: watcher.state().get("radioOk") is False)
    watcher.publish(f"{BASE}/set", '{"power": true}')
    assert wait_for(lambda: "CC1101 not found" in watcher.errors)
    assert service.radio.sent == []
    assert watcher.state()["power"] is False


def test_broker_outage_does_not_stop_the_timer(tmp_path):
    # Nothing is listening on this port: the safety timer must still run.
    StateStore(str(tmp_path / "state.json")).save(State(power=True), -1)
    config = Config(
        identity=TEST_IDENTITY,
        mqtt_host="127.0.0.1",
        mqtt_port=1,
        state_file=str(tmp_path / "state.json"),
        heartbeat_file=str(tmp_path / "heartbeat"),
    )
    radio = FakeRadio()
    service = Service(config, radio)
    thread = threading.Thread(target=service.run)
    thread.start()
    try:
        assert wait_for(lambda: radio.sent and radio.sent[0] == burst_for(State(power=False)))
    finally:
        service.stop()
        thread.join(timeout=15)
    assert not thread.is_alive()
