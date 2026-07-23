# Solar Irrigation 2.4

Solar Irrigation is a Home Assistant custom integration for conservative, weather-dependent garden irrigation. It estimates the total water demand for the current local calendar day from actual and forecast solar production, reduces demand when rain is measured, and exposes the internal calculation so the system can be tuned safely.

Version 2.4 uses a configurable **Automatic watering window** instead of the legacy single **Daily irrigation time**. The controller evaluates automatic irrigation every 15 minutes, reports `sleeping` outside that window, and cannot start automatic irrigation at night unless the user deliberately configures an overnight window. The rolling two-hour solar history, daily budget, persistent delivery counters, and writable **Peak daily water demand** remain the basis for pulse-and-soak development.

## Design goals

The integration is designed for beds and pots irrigated by a drip line or other low-flow system. Dry potting soil can become difficult to re-wet, and a long continuous run may pass through a pot before the growing medium has absorbed the water. The controller therefore treats calculated runtime as a **daily water budget**, not as an instruction that all water must be delivered in one uninterrupted run.

The algorithm separates four concerns:

1. **How much water may be needed today** — estimated from actual solar energy plus the remaining solar-production forecast.
2. **How strongly the sun has affected the garden recently** — estimated from 15-minute deltas of the cumulative daily solar-energy sensor, retained for two hours.
3. **How much water the crop and irrigation circuit need at peak seasonal demand** — controlled by the writable Peak daily water demand entity.
4. **How much has already been delivered today** — persisted and subtracted from the current budget.

## Inputs and parameters

### Daily solar energy sensor

A cumulative energy sensor representing solar production since the start of the day. Supported units are Wh, kWh and MWh; all values are normalized internally to kWh.

This sensor is used in two ways:

- Its current value contributes to the estimate of total solar production for today.
- Its increase between samples provides a proxy for recent solar radiation.

The source should reset daily. A negative delta is treated as a reset or source correction: the rolling history is cleared and a new baseline is established, so negative production can never influence irrigation.

### Remaining solar production forecast sensor

An energy sensor estimating how much additional solar energy will be produced during the remainder of the current day. Supported units are Wh, kWh and MWh.

This forecast is important early in the day. On a sunny morning, actual production may still be low, but a large remaining forecast allows the controller to allocate a realistic daily budget instead of waiting until the afternoon.

### Peak daily solar production

A fixed installation calibration in kWh/day. It represents a strong or peak production day for the configured photovoltaic system. It is normally configured once and only adjusted when the PV system, forecast source or calibration method changes.

The solar demand factor is:

```text
estimated total solar = actual solar today + forecast remaining solar
solar factor = clamp(estimated total solar / peak daily solar production, 0, 1)
```

A factor of 0.50 means the estimated solar conditions correspond to roughly half of the configured peak-production day. Values above the peak reference are capped at 1.0.

### Peak daily water demand

A writable Home Assistant number entity with an allowed range of **10–240 minutes per day**, in one-minute steps.

This is the main seasonal tuning control. It means:

> The total pump-on time required by this irrigation circuit on a peak-demand day before rain reduction.

It has two simultaneous roles:

- **Seasonal scale factor:** increase it as crop size, leaf area and root mass increase; reduce it for seedlings or late-season decline.
- **Safety ceiling:** automatic irrigation must not deliver more than this amount during one local calendar day.

Changing the value persists it through Home Assistant restarts and immediately reloads the integration so the daily and remaining budgets are recalculated. An active irrigation run is not lengthened or shortened; only future automatic decisions use the new value.

Typical tuning examples are installation-specific, but a progression might be lower values for seedlings, larger values for mature fruiting tomatoes and corn, and lower values again late in the season.

### Rain sensor (optional)

A cumulative or daily rain sensor supporting mm, cm or inches. The value is normalized to millimetres.

When configured, rain reduces the daily budget linearly until the configured rain skip threshold is reached:

```text
rain factor = clamp(1 - rain / rain skip threshold, 0, 1)
```

At or above the threshold, the rain factor is zero and automatic irrigation is blocked. When no rain sensor is configured, the rain factor is 1.0. If a configured rain sensor is unavailable, automatic calculation fails safely rather than assuming no rain.

### Rain skip threshold

The amount of measured rain that reduces the automatic daily water budget to zero. Half of this amount produces approximately a 50% rain factor.

### Update interval

The requested coordinator refresh period in seconds. Solar Irrigation samples the cumulative solar sensor at least every 15 minutes, so a longer configured interval is internally limited to 15 minutes for solar-history collection. Shorter coordinator updates do not create excessive samples: a new delta is accepted only after the minimum sampling interval has elapsed.

### Automatic watering window start

The earliest local time at which automatic irrigation is permitted. The default is `05:00:00`. The 15-minute evaluator may therefore make its first automatic decision at the first evaluation on or after this time. Manual `run_now` service calls are not restricted by the window.

### Automatic watering window end

The local time at which new automatic irrigation becomes blocked. The default is `22:00:00`. The end is exclusive: with a `05:00-22:00` window, an evaluation at exactly 22:00 enters `sleeping` and does not start a run. An irrigation run that began before the window closed is allowed to finish safely.

Both normal daytime windows and windows that cross midnight are supported. For example, `22:00-05:00` is an overnight window. Equal start and end times are rejected because they are ambiguous and would not provide a safe sleep period.

### Automatic evaluation interval

The automatic scheduler evaluates every 15 minutes. Each evaluation first checks the local watering window. Outside the window it updates controller status to `sleeping` with decision reason `outside_watering_window`. Inside the window it reports `monitoring`, refreshes source data when an automatic decision is eligible, and applies the daily-decision guard.

Version 2.4 retains the existing one-automatic-decision-per-day execution behavior while moving the timer architecture to periodic evaluation. This avoids an unexpected change in delivered water before the full multi-pulse allocator is implemented, while establishing the correct time-window and sleep-state foundation.

## Daily budget algorithm

The estimated total solar production is calculated from both actual and forecast energy:

```text
estimated_total_solar_kwh = actual_solar_kwh + remaining_forecast_kwh
```

The value is normalized against Peak daily solar production:

```text
solar_factor = clamp(
    estimated_total_solar_kwh / peak_daily_solar_production_kwh,
    0,
    1,
)
```

Rain is converted into a multiplier from 1.0 down to 0.0. The daily budget is then:

```text
daily_water_budget_minutes =
    peak_daily_water_demand_minutes
    × solar_factor
    × rain_factor
```

The remaining automatic budget is:

```text
remaining_budget_minutes = max(
    0,
    daily_water_budget_minutes - delivered_today_minutes,
)
```

If a later forecast revision reduces the budget below the amount already delivered, the remaining budget becomes zero. The integration never attempts to “undo” irrigation and performs no further automatic watering that day.

## Rolling two-hour solar history

Every accepted sample stores:

- timestamp;
- cumulative energy in kWh;
- energy delta since the previous baseline;
- elapsed seconds;
- normalized production rate in kWh/h.

Samples older than two hours are removed by timestamp. This is safer than retaining exactly eight records because Home Assistant may restart or updates may be delayed.

The integration calculates and exposes:

- latest accepted energy delta;
- energy produced in the last hour;
- energy produced in the last two hours;
- average rate during each window;
- weighted rolling rate: 70% last-hour rate and 30% two-hour rate;
- sample count and full timestamped history.

The rolling signal is intentionally observational in 2.4. It provides the data required to tune the next pulse-and-soak scheduler without introducing opaque rapid-change heuristics.

## Daily reset and persistence

The water-delivery counters are tied to Home Assistant local calendar time. When the stored delivery date differs from the current local date, the controller resets:

- delivered runtime today;
- pulse count today;
- the available daily budget calculation for the new day.

Unused budget is never carried into the following day. The last execution result and historical diagnostic information may remain visible, but they do not add water to the new day.

The reset is also checked during startup, making it safe when Home Assistant was offline at midnight. Controller state and solar history are stored per config entry.

## Controller states and observability

The controller status describes what the controller is doing now rather than leaving it permanently in a historical `completed` state. Version 2.4 defines meaningful states including:

- `initializing`
- `waiting_for_history`
- `sleeping`
- `monitoring`
- `waiting_for_pulse`
- `soaking`
- `irrigating`
- `rain_paused`
- `daily_budget_reached`
- `error`

Legacy `idle`, `scheduled`, `running` and `completed` values are migrated safely when persisted state is loaded.

Diagnostic entities expose the values needed to explain decisions:

- expected, actual and remaining solar energy;
- solar and rain factors;
- calculated daily water budget;
- delivered and remaining budget;
- pulse count;
- one-hour and two-hour solar metrics;
- complete two-hour sample history;
- controller status and decision reason.

The guiding principle is that every irrigation decision should be explainable from visible Home Assistant state.

## Manual services

### `solar_irrigation.run_now`

Starts a manual run for a selected config entry. An optional duration overrides the calculated runtime. `ignore_rain` allows an explicit operator test or emergency run despite rain protection.

Manual runs are deliberate overrides. They are measured and visible in controller state, but the current service behavior is separate from the scheduled automatic decision guard.

### `solar_irrigation.stop`

Stops an active run, turns off or closes the configured irrigation entity, records actual elapsed delivery, and returns the controller to the monitoring state.

## Upgrade notes for 2.4

- The separate **Solar sample count** entity has been removed because the **Solar history** entity already exposes the accepted sample count as its state.
- The complete rolling sample list remains available in the **Solar history** entity attributes and in downloaded diagnostics.

- The manifest version is `2.4`.
- `Daily irrigation time` is removed from new and updated configuration forms.
- Existing `schedule_time` data is migrated automatically to **Automatic watering window start**. This preserves the previous earliest automatic run time.
- **Automatic watering window end** defaults to `22:00:00` during migration.
- Config-entry schema version is increased to `2`.
- Automatic evaluation runs every 15 minutes and is blocked outside the configured window.
- Controller status becomes `sleeping` at night and `monitoring` while the window is open.
- Manual `run_now` and `stop` services remain available outside the automatic window.
- Daily delivered-water counters and budget reset behavior remain tied to Home Assistant local calendar days.

## Development and validation

```bash
make setup_test_env
make test
make test-hassfest
```

The integration is intentionally conservative: unavailable required data, invalid units, negative deltas and control-service failures must fail safely and remain visible through logs and diagnostics.
