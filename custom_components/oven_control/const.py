"""Constants for the Oven Control integration."""

from typing import Final

DOMAIN: Final = "oven_control"

# Polling intervals, adjustable in the options flow.
CONF_STATUS_INTERVAL: Final = "status_interval"
CONF_SETTINGS_INTERVAL: Final = "settings_interval"
DEFAULT_STATUS_INTERVAL: Final = 10  # seconds
DEFAULT_SETTINGS_INTERVAL: Final = 5  # minutes
# The controller serves one client at a time; faster polling starves the vendor app.
MIN_STATUS_INTERVAL: Final = 5
MAX_STATUS_INTERVAL: Final = 300
MIN_SETTINGS_INTERVAL: Final = 1
MAX_SETTINGS_INTERVAL: Final = 60

# Manufacturer ids used by the controller (see the vendor app's model table).
MANUFACTURERS: Final = {1: "UNIVERSAL", 8: "OFEN INNOVATIV"}

# Relay modes of the DG relay (flue-gas fan / extractor hood), cmd 0x12/0x13.
RELAY_MODES: Final = [
    "off",
    "hood_combustion",
    "hood_door",
    "flue_fan_start_temp",
    "flue_fan_combustion",
]

# Buffer sensor that controls the pump (water variant), cmd 0x20/0x21.
BOILER_SENSORS: Final = ["t4_top", "t7_bottom"]
