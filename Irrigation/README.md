# Solar Irrigation

Solar Irrigation is a Home Assistant custom integration that calculates an irrigation runtime from current and forecast solar energy, optionally reduces that runtime using measured rain, and controls a configured switch or valve on a daily schedule.

## Inputs

- Solar energy produced: Wh, kWh, or MWh.
- Remaining solar forecast: Wh, kWh, or MWh.
- Irrigation entity: switch or valve.
- Rain sensor: optional; supports mm, cm, or inches.

When no rain sensor is configured, irrigation uses solar data only. When a rain sensor is configured and unavailable, coordinator data becomes unavailable and automatic irrigation does not start.

## Calculation

The integration normalizes solar energy to kWh, calculates a solar factor against the configured maximum, then multiplies the maximum runtime by the solar factor. With rain configured, the runtime is reduced linearly until the rain skip threshold is reached.

## Services

- `solar_irrigation.run_now`: manually start a calculated or overridden run.
- `solar_irrigation.stop`: stop the active run.

## Development

```bash
make setup_test_env
make test
make test-hassfest
```
