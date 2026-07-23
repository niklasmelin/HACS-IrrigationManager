# Solar history and observability implementation

This build adds the foundation for pulse-and-soak scheduling without changing the current automatic watering behavior yet.

## Added

- A persisted 15-minute cumulative-energy sampler.
- Two hours of timestamped solar-energy deltas.
- Reset detection for daily cumulative-energy sensors.
- Normalized hourly production rates for delayed samples.
- Diagnostic entities for one-hour and two-hour solar production.
- Diagnostic entities for daily budget, delivered runtime, remaining runtime, pulse count, and decision reason.
- Full solar history in entity attributes and downloaded diagnostics.
- Persistent daily delivered-runtime and pulse counters.

## Sampling behavior

The coordinator refreshes at least every 15 minutes. A new sample is accepted after at least 12 minutes, allowing normal Home Assistant scheduling jitter. The history is pruned by timestamp to two hours.

The rolling rate is currently:

```text
0.7 * last_hour_rate + 0.3 * last_two_hour_rate
```

This build does not yet use the rolling solar rate to schedule multiple automatic pulses. It makes the required state observable and persistent so the pulse scheduler can be tuned safely in the next change.
