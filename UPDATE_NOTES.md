# Update notes

## Version 2.6.0

- Adds writable **Maximum pulse duration** and **Soak duration** number entities.
- Maximum pulse duration: 0.5-15 minutes, 0.5-minute steps, default 3 minutes.
- Soak duration: 1-30 minutes, one-minute steps, default 15 minutes.
- Changes are persisted without reloading the integration.
- A running pulse or soak is not altered; the new setting applies to the next stage.
- Existing values outside the new limits are clamped when read or changed.

# Solar Irrigation 2.5

- Implements serialized pulse-and-soak watering events.
- Re-evaluates automatic need every 15 minutes without overlapping active cycles.
- Enforces the shared manual/automatic daily water budget before every automatic pulse.
- Confirms physical actuator state and reconciles external state changes.
- Corrects `ignore_rain` behavior with calculated or explicit duration.
- Adds maximum pulse and soak options.
- Uses human-friendly config-entry selectors for actions while retaining legacy YAML compatibility.
- Adds immediate push updates for controller observability.
- Proportionally handles delayed cumulative-solar samples.
- Expands tests for state-machine, scheduler, validation, diagnostics, and restart behavior.
- Keeps controller status at Irrigating until the physical stop is confirmed and
  accounts actuator stop latency in actual delivered time.
- Preserves active timing after a failed stop so a later external off or restart
  can account the complete pulse.
- Rebuilds coarse solar history from the exact cumulative value since local
  midnight after setup, restart, or daily reset.
- Migrates config entries to schema version 3 and clamps legacy peak-demand
  values to the supported range.
- Hides Peak daily water demand from the options form after setup; the writable
  number entity is now the single seasonal tuning control.
- Normalizes legacy config-entry unique IDs to the selected actuator and blocks
  duplicate-actuator migrations.
- Validates valve entities for entity-level OPEN and CLOSE support.
- Counts a still-active actuator through confirmed restart recovery, including
  runtime beyond the originally requested pulse after a failed stop.
