# Home Assistant HACS Custom Integration
# Project: Solar Irrigation Optimizer

## Goal

Create a Home Assistant custom integration distributed through HACS that automatically determines the required irrigation duration based on how much solar energy is (or is expected to be) produced during the current day.

The philosophy is simple:

> More sun → More evaporation → More irrigation.

Instead of using weather forecasts directly, use the home's photovoltaic production as the indicator of solar radiation.

---

# Functional Overview

The integration shall:

- Calculate expected total solar energy for today.
- Calculate a scale factor relative to a configurable "perfect sunny day".
- Calculate irrigation runtime.
- Automatically start an irrigation switch/entity.
- Stop irrigation when calculated runtime has elapsed.

The integration shall expose all intermediate values as sensors.

---

# Integration Name

Suggested domain:

solar_irrigation

Repository:

ha-solar-irrigation

---

# HACS Requirements

Follow current Home Assistant integration best practices.

Required files:

custom_components/
    solar_irrigation/
        __init__.py
        manifest.json
        config_flow.py
        coordinator.py
        sensor.py
        switch.py (optional)
        services.yaml
        const.py
        irrigation.py
        strings.json
        translations/
            en.json
README.md
LICENSE
hacs.json

Use Config Entries only.
Do NOT use YAML configuration.

---

# hacs.json

Version bumping
Always bump the version in the hacs.json file when releasing a new version of the integration. Use semantic versioning (e.g., 0.1, 0.2 etc.). 
1. Minior version for no-braking changes 0.X
2. Major version for breaking changes Y.0 
Ask if you are unsure if the changes are breaking or not.


Content of hacs.json:
{
  "name": "Solar Irrigation",
  "description": "Automatically determines irrigation duration based on solar energy production.",
  "documentation": "https://github.com/niklasmelin/HACS-IrrigationManager",
  "country": "SE",
  "categories": ["sensor", "switch"],
  "version": "X.Y",
  "codeowners": ["@niklasmelin"],
  "homeassistant": "2026.06.0"
}

---

# Configuration Flow

The integration shall require the following inputs.

## 1. Solar production today sensor

Entity selector:

sensor

Purpose:

Actual produced PV energy today.

Example:

sensor.solar_energy_today

Expected unit:

kWh

Mandatory.

---

## 2. Remaining solar production today sensor

Entity selector:

sensor

Purpose:

Forecast remaining PV production today.

Example:

sensor.remaining_solar_today

Expected unit:

kWh

Mandatory.

---

## 3. Irrigation entity

Entity selector:

switch

Purpose:

Controls irrigation pump.

Example:

switch.irrigation_pump

Mandatory.

---

## 4. Maximum daily solar production

Numeric input

Default:

65

Unit:

kWh

Mandatory.

Description:

Represents an exceptionally sunny day.

---

## 5. Maximum irrigation runtime

Numeric input

Default:

60

Unit:

minutes

Mandatory.

Represents watering required during a perfect sunny day.

---

## 6. Update interval

Optional.

Default:

1 hour

Used for recalculating irrigation duration.

---

# Data Model

Read

Current Solar Energy

from sensor #1

Example

38.2 kWh

Read

Remaining Solar Energy

from sensor #2

Example

17.5 kWh

Compute

Total Solar Energy Today

TotalSolar =
CurrentSolar
+
RemainingSolar

Example

55.7 kWh

---

# Control Algorithm

ScaleFactor =
TotalSolar
/
MaximumDailySolar

Clamp

0.0

to

1.0

Then

RuntimeMinutes =
ScaleFactor
×
MaximumRuntime

Example

MaximumDailySolar = 65

TotalSolar = 55

ScaleFactor

55 / 65

=

0.846

MaximumRuntime = 60

Runtime

=

50.8 minutes

Round to nearest second.

---

# Irrigation Logic

Choose one execution time every day.

Recommended:

06:00 local time.

Workflow:

06:00

↓

Read sensors

↓

Calculate runtime

↓

Turn irrigation switch ON

↓

Wait calculated runtime

↓

Turn irrigation switch OFF

No further watering that day.

---

# Recalculation Behaviour

If Home Assistant starts after 06:00 but irrigation has not yet run today:

Run immediately.

If irrigation already completed today:

Do nothing.

Store last execution date using Home Assistant storage.

---

# Sensors to Expose

Create diagnostic sensors.

## Expected Solar Today

expected_solar_today

Unit

kWh

Value

CurrentSolar + RemainingSolar

---

## Scale Factor

solar_scale_factor

Range

0.0–1.0

---

## Irrigation Runtime

irrigation_runtime

Unit

minutes

---

## Irrigation Runtime Seconds

irrigation_runtime_seconds

Unit

seconds

---

## Irrigation Status

Values

Idle

Scheduled

Running

Completed

---

## Last Irrigation

Timestamp

---

# Coordinator

Implement a DataUpdateCoordinator.

Responsibilities:

Read both energy sensors

Perform calculations

Publish calculated values

Notify entities

---

# Irrigation Controller

Implement a dedicated controller class.

Responsibilities:

Scheduling

State machine

Runtime timer

Switch control

Persistence

Avoid putting logic inside sensor entities.

---

# Error Handling

Detect

Unavailable sensors

Unknown sensor values

Negative values

Non-numeric values

Switch unavailable

If calculations cannot be made:

Do NOT start irrigation.

Expose sensor state as unavailable.

Write informative log entries.

---

# Logging

Use LOGGER.

Log

configuration

calculated runtime

switch ON

switch OFF

errors

restart recovery

---

# Home Assistant Services

Provide a service

solar_irrigation.run_now

Runs irrigation immediately using the latest calculated runtime.

Provide

solar_irrigation.stop

Stops irrigation immediately.

---

# Diagnostics

Implement diagnostics support.

Include

configuration

current calculations

runtime

last execution

sensor values

---

# README

Include

Purpose

Installation via HACS

Configuration

Example

How calculations work

Troubleshooting

Screenshots

---

# Testing

Create pytest tests for

Calculation algorithm

Scale factor

Clamping

Runtime calculation

Unavailable sensors

Recovery after restart

Service calls

Scheduler

---

# Coding Style

Follow Home Assistant development guidelines.

Requirements

Type hints everywhere

Dataclasses where appropriate

No global mutable state

Black formatting

Ruff clean

MyPy friendly

Use async APIs

Avoid blocking calls

---

# Future Extensions (Not implemented now)

Support multiple irrigation zones.

Support soil moisture sensor.

Support rain sensor.

Support weather forecast weighting.

Support configurable watering time.

Support adaptive learning.

Support irrigation history graphs.

Support Lovelace dashboard card.

Support manual runtime multiplier.

Support seasonal adjustment.

These should be designed for future extensibility but excluded from the initial implementation.

---

# Acceptance Criteria

The integration is complete when:

✓ Installable through HACS

✓ Config Flow works

✓ Reads both configured sensors

✓ Calculates expected solar energy

✓ Calculates irrigation runtime

✓ Starts irrigation automatically once per day

✓ Stops irrigation after calculated runtime

✓ Exposes diagnostic sensors

✓ Survives Home Assistant restart

✓ Can be manually started and stopped via services

✓ Includes tests and documentation

✓ Passes Home Assistant quality standards
