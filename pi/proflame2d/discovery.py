"""Home Assistant MQTT discovery. HA builds the fireplace device from these messages."""
import json

NODE_ID = "proflame2_fireplace"


def _number(name: str, key: str, icon: str) -> tuple[str, str, dict]:
    return (
        "number",
        key,
        {
            "name": name,
            "icon": icon,
            "min": 0,
            "max": 6,
            "step": 1,
            "mode": "slider",
            "command_template": f'{{"{key}": {{{{ value | int }}}}}}',
            "value_template": f"{{{{ value_json.{key} }}}}",
        },
    )


def _switch(name: str, key: str, icon: str) -> tuple[str, str, dict]:
    return (
        "switch",
        key,
        {
            "name": name,
            "icon": icon,
            "payload_on": json.dumps({key: True}),
            "payload_off": json.dumps({key: False}),
            "state_on": "ON",
            "state_off": "OFF",
            "value_template": f"{{{{ 'ON' if value_json.{key} else 'OFF' }}}}",
        },
    )


# pilot is left out on purpose: it's a burner setting, not something to flip from a dashboard.
_ENTITIES = (
    _switch("Power", "power", "mdi:fireplace"),
    _number("Flame", "flame", "mdi:fire"),
    _switch("Front burner", "front", "mdi:fire-circle"),
    _number("Fan", "fan", "mdi:fan"),
    _number("Light", "light", "mdi:lightbulb"),
    _switch("Aux", "aux", "mdi:power-socket-us"),
    (
        "sensor",
        "auto_off",
        {
            "name": "Auto-off in",
            "device_class": "duration",
            "unit_of_measurement": "s",
            "entity_category": "diagnostic",
            "value_template": "{{ value_json.autoOffRemainingS }}",
        },
    ),
    (
        "binary_sensor",
        "radio_problem",
        {
            "name": "Radio problem",
            "device_class": "problem",
            "entity_category": "diagnostic",
            "payload_on": "ON",
            "payload_off": "OFF",
            "value_template": "{{ 'OFF' if value_json.radioOk else 'ON' }}",
        },
    ),
)


def discovery_messages(discovery_prefix: str, base_topic: str) -> list[tuple[str, str]]:
    """Returns (topic, payload) pairs, to publish retained."""
    device = {
        "identifiers": [NODE_ID],
        "name": "Fireplace",
        "manufacturer": "SIT",
        "model": "Proflame 2 (via CC1101)",
    }
    messages = []
    for component, key, fields in _ENTITIES:
        payload = {
            "unique_id": f"{NODE_ID}_{key}",
            "device": device,
            "state_topic": f"{base_topic}/state",
            "availability_topic": f"{base_topic}/availability",
            **fields,
        }
        if component in ("switch", "number"):
            payload["command_topic"] = f"{base_topic}/set"
        messages.append(
            (f"{discovery_prefix}/{component}/{NODE_ID}/{key}/config", json.dumps(payload))
        )
    return messages
