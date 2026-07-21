# Solar Irrigation Integration

## Goal

Create a Home Assistant custom integration distributed through HACS that automatically determines the required irrigation duration based on how much solar energy is (or is expected to be) produced during the current day.

The philosophy is simple:

> More sun → More evaporation → More irrigation.

Instead of using weather forecasts directly, use the home's photovoltaic production as the indicator of solar radiation.

## Functional Overview

The integration shall:

- Calculate expected total solar energy for today.
- Calculate a scale factor relative to a configurable "perfect sunny day".
- Calculate irrigation runtime.
- Automatically start an irrigation switch/entity.
- Stop irrigation when calculated runtime has elapsed.

The integration shall expose all intermediate values as sensors.

## Integration Name

Suggested domain:

solar_irrigation

Repository:

ha-solar-irrigation

## HACS Requirements

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