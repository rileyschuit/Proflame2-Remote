"""Runs the fireplace: MQTT commands in, radio frames out, safety timer always on.

Same rules and topics as esp32s3_mqtt_rest (docs/interfaces.md), so both builds behave the
same. One loop owns the controller and radio; the MQTT thread only queues messages.
"""
import json
import logging
import os
import queue
import threading
import time
from typing import Protocol

import paho.mqtt.client as mqtt

from .config import Config
from .controller import CommandError, Controller, apply_fields
from .discovery import discovery_messages
from .store import StateStore

log = logging.getLogger(__name__)

_LOOP_S = 0.05
_STATE_REFRESH_S = 30.0
_RADIO_RETRY_S = 30.0
_HEARTBEAT_S = 5.0
_SHUTDOWN_S = 8.0
_MAX_PAYLOAD_BYTES = 256


class Radio(Protocol):
    present: bool
    version: int

    def begin(self, frequency_khz: int, power: str) -> bool: ...

    def transmit(self, data: bytes) -> bool: ...


class Service:
    def __init__(self, config: Config, radio: Radio):
        self._config = config
        self._radio = radio
        self._commands: queue.Queue[bytes | Exception] = queue.Queue()
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._store = StateStore(config.state_file)
        self._controller = Controller(
            config.identity, radio.transmit, time.monotonic, config.auto_off_minutes
        )
        self._set_topic = f"{config.base_topic}/set"
        self._state_topic = f"{config.base_topic}/state"
        self._availability_topic = f"{config.base_topic}/availability"
        self._error_topic = f"{config.base_topic}/error"
        self._client = self._build_client()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        saved = self._store.load()
        if saved:
            # Nothing is sent at startup, unless the timer ran out while we were down.
            self._controller.restore(*saved)
            log.info("restored state: %s", saved[0])
        self._start_radio()

        self._client.connect_async(self._config.mqtt_host, self._config.mqtt_port)
        self._client.loop_start()
        try:
            self._loop()
        finally:
            self._shut_down()

    def _build_client(self) -> mqtt.Client:
        # Clean session: no queued commands waiting for us after an outage.
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="proflame2d", clean_session=True
        )
        if self._config.mqtt_user:
            client.username_pw_set(self._config.mqtt_user, self._config.mqtt_password)
        client.will_set(self._availability_topic, "offline", qos=1, retain=True)
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        return client

    def _start_radio(self) -> None:
        found = self._radio.begin(self._config.frequency_khz, self._config.tx_power)
        if found:
            log.info("CC1101 found, version %d", self._radio.version)
        else:
            log.warning("CC1101 NOT FOUND, check the wiring; retrying every %ds", _RADIO_RETRY_S)

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties) -> None:
        if reason_code.is_failure:
            log.error("MQTT connect refused: %s", reason_code)
            return
        log.info("MQTT connected")
        client.subscribe(self._set_topic, qos=0)
        self._connected.set()

    def _on_message(self, _client, _userdata, message) -> None:
        # A stale "power on" kept by the broker must not relight the fireplace.
        if message.retain:
            self._commands.put(CommandError("retained commands are refused"))
        elif len(message.payload) > _MAX_PAYLOAD_BYTES:
            self._commands.put(CommandError("payload too large"))
        else:
            self._commands.put(bytes(message.payload))

    def _loop(self) -> None:
        last_radio_try = last_state = last_heartbeat = time.monotonic()
        published_state = None
        saved_state = self._controller.state
        while not self._stop.is_set():
            self._drain_commands()
            self._controller.tick()

            if self._controller.state != saved_state:
                saved_state = self._controller.state
                self._save()

            now = time.monotonic()
            if not self._radio.present and now - last_radio_try >= _RADIO_RETRY_S:
                last_radio_try = now
                self._start_radio()

            if self._connected.is_set():
                self._connected.clear()
                self._publish_online()
                published_state = None

            current = self._state_json(include_timer=False)
            if current != published_state or now - last_state >= _STATE_REFRESH_S:
                self._client.publish(self._state_topic, self._state_json(), qos=0, retain=True)
                published_state = current
                last_state = now

            if now - last_heartbeat >= _HEARTBEAT_S:
                self._beat()
                last_heartbeat = now
            self._stop.wait(_LOOP_S)

    def _drain_commands(self) -> None:
        while True:
            try:
                item = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                self._apply(item)
            except CommandError as error:
                log.warning("command refused: %s", error)
                self._client.publish(self._error_topic, str(error), qos=0)

    def _apply(self, item: bytes | Exception) -> None:
        if isinstance(item, Exception):
            raise item
        try:
            fields = json.loads(item)
        except ValueError as error:
            raise CommandError("invalid JSON") from error
        next_state = apply_fields(self._controller.state, fields)
        # An off is still taken: the controller keeps retrying until the radio is back.
        if next_state.power and not self._radio.present:
            raise CommandError("CC1101 not found")
        self._controller.commit(next_state)

    def _publish_online(self) -> None:
        for topic, payload in discovery_messages(
            self._config.discovery_prefix, self._config.base_topic
        ):
            self._client.publish(topic, payload, qos=1, retain=True)
        self._client.publish(self._availability_topic, "online", qos=1, retain=True)

    def _state_json(self, include_timer: bool = True) -> str:
        state = self._controller.state
        document = {
            "power": state.power,
            "flame": state.flame,
            "fan": state.fan,
            "light": state.light,
            "front": state.front,
            "aux": state.aux,
            "pilot": state.pilot,
            "autoOffMinutes": self._controller.auto_off_minutes,
            "radioOk": self._radio.present and self._controller.last_transmit_ok,
            # Only what this device last sent. The real remote can change the fireplace.
            "assumed": True,
        }
        if include_timer:
            document["autoOffRemainingS"] = int(self._controller.remaining_s())
        return json.dumps(document)

    def _save(self) -> None:
        try:
            self._store.save(self._controller.state, self._controller.remaining_s())
        except OSError as error:
            log.error("could not save state: %s", error)

    def _beat(self) -> None:
        try:
            with open(self._config.heartbeat_file, "w", encoding="utf-8") as handle:
                handle.write(str(time.time()))
        except OSError as error:
            log.error("could not write heartbeat: %s", error)

    def _shut_down(self) -> None:
        # Nothing runs the auto-off timer once this exits, so don't leave a fire burning.
        if self._controller.state.power:
            log.warning("stopping with the fireplace on: turning it off first")
            self._controller.off_with_resends()
            deadline = time.monotonic() + _SHUTDOWN_S
            while self._controller.pending and time.monotonic() < deadline:
                self._controller.tick()
                time.sleep(_LOOP_S)
            self._save()
        self._client.publish(self._state_topic, self._state_json(), qos=0, retain=True)
        offline = self._client.publish(self._availability_topic, "offline", qos=1, retain=True)
        if self._client.is_connected():
            # A clean disconnect doesn't fire the last will, so this has to reach the broker.
            offline.wait_for_publish(timeout=2)
        self._client.disconnect()
        self._client.loop_stop()
        if os.path.exists(self._config.heartbeat_file):
            os.unlink(self._config.heartbeat_file)
