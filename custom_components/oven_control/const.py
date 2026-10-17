"""Constants for the Oven Control integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "oven_control"

STATUS_INTERVAL: Final = timedelta(seconds=10)
SETTINGS_INTERVAL: Final = timedelta(minutes=5)

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
