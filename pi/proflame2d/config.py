"""Settings, all from environment variables. See docs/pi_service.md."""
import os
from dataclasses import dataclass
from typing import Mapping

from .cc1101 import DEFAULT_FREQUENCY_KHZ, PA_LEVELS
from .controller import DEFAULT_AUTO_OFF_MINUTES
from .frame import Identity

_PREFIX = "PROFLAME2_"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    identity: Identity
    mqtt_host: str
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    base_topic: str = "home/fireplace"
    discovery_prefix: str = "homeassistant"
    auto_off_minutes: int = DEFAULT_AUTO_OFF_MINUTES
    frequency_khz: int = DEFAULT_FREQUENCY_KHZ
    tx_power: str = "low"
    spi_bus: int = 0
    spi_device: int = 0
    state_file: str = "/data/state.json"
    heartbeat_file: str = "/run/proflame2/heartbeat"


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(_PREFIX + name, "")
    if not value:
        raise ConfigError(f"{_PREFIX}{name} is required")
    return value


def _number(env: Mapping[str, str], name: str, default: int | None = None, base: int = 10) -> int:
    raw = env.get(_PREFIX + name, "")
    if not raw:
        if default is None:
            raise ConfigError(f"{_PREFIX}{name} is required")
        return default
    try:
        return int(raw, base)
    except ValueError as error:
        raise ConfigError(f"{_PREFIX}{name} must be a number") from error


def _nibble(env: Mapping[str, str], name: str) -> int:
    value = _number(env, name, base=16)
    if not 0 <= value <= 0xF:
        raise ConfigError(f"{_PREFIX}{name} must be one hex digit")
    return value


def load(env: Mapping[str, str] = os.environ) -> Config:
    serial = _number(env, "SERIAL", base=16)
    if not 0 <= serial <= 0xFFFFFF:
        raise ConfigError(f"{_PREFIX}SERIAL must fit in 24 bits")
    tx_power = env.get(_PREFIX + "TX_POWER", "low")
    if tx_power not in PA_LEVELS:
        raise ConfigError(f"{_PREFIX}TX_POWER must be one of {sorted(PA_LEVELS)}")
    defaults = Config(identity=Identity(0, 0, 0, 0, 0), mqtt_host="")
    return Config(
        identity=Identity(
            serial,
            _nibble(env, "ERR1_C"),
            _nibble(env, "ERR1_D"),
            _nibble(env, "ERR2_C"),
            _nibble(env, "ERR2_D"),
        ),
        mqtt_host=_required(env, "MQTT_HOST"),
        mqtt_port=_number(env, "MQTT_PORT", defaults.mqtt_port),
        mqtt_user=env.get(_PREFIX + "MQTT_USER", ""),
        mqtt_password=env.get(_PREFIX + "MQTT_PASSWORD", ""),
        base_topic=env.get(_PREFIX + "BASE_TOPIC", defaults.base_topic).rstrip("/"),
        discovery_prefix=env.get(_PREFIX + "DISCOVERY_PREFIX", defaults.discovery_prefix),
        auto_off_minutes=_number(env, "AUTO_OFF_MINUTES", defaults.auto_off_minutes),
        frequency_khz=_number(env, "FREQUENCY_KHZ", defaults.frequency_khz),
        tx_power=tx_power,
        spi_bus=_number(env, "SPI_BUS", defaults.spi_bus),
        spi_device=_number(env, "SPI_DEVICE", defaults.spi_device),
        state_file=env.get(_PREFIX + "STATE_FILE", defaults.state_file),
        heartbeat_file=env.get(_PREFIX + "HEARTBEAT_FILE", defaults.heartbeat_file),
    )
