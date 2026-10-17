# Oven Control – Home Assistant integration for Ofen Innovativ stoves

Local Home Assistant integration for wood stove controllers by Firecontrols, as sold with
Ofen Innovativ stoves and used by the "ofeninnovativ" Android app. It talks to the controller's
Wi-Fi module over plain HTTP in your home network – no cloud.

> **Status: early.** Reading values is tested against a real controller (WIZnet module,
> firmware "Converter Wifire 1.3.2", MCU version 32). **Writing settings is implemented like
> the vendor app does it, but has not been tried on a real device yet.** Change settings only
> while you can watch the stove, and compare with the app.

Requires Home Assistant 2026.10 or newer.

## Installation

### HACS

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/MichScha/oven-control`, type
   *Integration*.
2. Install *Oven Control (Ofen Innovativ)* and restart Home Assistant.

### Manual

Copy `custom_components/oven_control` into the `custom_components` folder of your Home
Assistant configuration and restart Home Assistant.

## Set-up

1. Connect the controller to your home Wi-Fi with the vendor app (*Einstellungen → WLAN Netz*).
2. Give it a fixed IP address in your router (DHCP reservation).
3. *Settings → Devices & services → Add integration → Oven Control*, enter the IP address.

The integration identifies the controller by its `device-id`, so a second set-up of the same
controller is refused. If the IP address changes, use *Reconfigure* on the integration entry
(or add it again with the new address – the existing entry is updated).

The controller handles **one client at a time**. While the vendor app is open on a phone, the
controller may drop connections; the integration retries, and entities may become unavailable
for a short time.

## Entities

| Entity | Notes |
|---|---|
| Flame temperature, air flap, burn phase, burn duration | updated every 10 s |
| Door, relay DG (flue-gas fan / extractor hood) | binary sensors |
| Heating error, flame sensor error | problem sensors from the live alarm bits |
| Latest alarm | date of the newest alarm-log entry; the last 10 entries as attributes |
| Alarm bits, alarm 2, flap position (raw), device clock, Wi-Fi | diagnostic |
| TS, S2–S5, DS3–DS5, SS2, SZV | burn curve as number entities (configuration) |
| Relay mode | select (configuration) |
| Alarm switches | alarm mask as in the app's *Set Alarme*, disabled by default |
| Sync device clock | button; refused while a burn is being controlled |

Water-heating units (boiler / buffer) additionally get T2/T4/T7 temperatures, the circulation
pump, boiler and buffer overheat sensors, pump on/off temperature and the pump control sensor.
They are only created when the controller reports the water variant.

Settings are read every 5 minutes. The burn phase is the raw number of the controller; known
so far: `1` = start, waiting for the start temperature TS; `8` = stopped (e.g. after TS was
not reached within 45 minutes, together with a heating error).

Not exposed on purpose: output test, alarm/archive/factory resets, resetting the burn curve,
changing the stove model, and all Wi-Fi/access-point settings – use the vendor app for those.

## Security

The controller has **no authentication**. Anyone in the same network can read and change its
settings. Its endpoint `/module/config` also returns the **home Wi-Fi password and the
access-point password in clear text**. The integration never reads that endpoint, and
diagnostics leave out IP addresses, SSIDs and keys – but consider putting the stove in a
separate network for IoT devices.

## Development

```sh
make test   # creates .venv with Python 3.14 (via mise) and runs the tests
```
