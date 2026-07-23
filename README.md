# Solar Irrigation

Solar Irrigation is a Home Assistant custom integration for conservative,
weather-dependent garden irrigation. It combines measured solar production, the
forecast solar production remaining for the day, optional rain, and a seasonal
water-demand setting. The resulting daily pump-runtime budget is delivered as
short watering pulses separated by soak periods.

Version **2.6.0** implements the complete pulse-and-soak controller, shared daily
budget accounting for automatic and manual watering, physical pump-state
confirmation, immediate controller observability, and config-entry selectors for
manual actions.

## Why pulse and soak?

Dry soil, especially potting soil, can initially repel water. One long continuous
run may pass through a pot or follow cracks in a bed before the root zone has time
to absorb it. Solar Irrigation therefore divides one watering event into several
short pump-on periods:

```text
water pulse -> soak -> water pulse -> soak -> final water pulse
```

Only pump-on time consumes the daily water budget. The pump is off during each
soak interval.

Example with a seven-minute event, a three-minute maximum pulse, and a 15-minute
soak interval:

```text
3 min water
15 min soak
3 min water
15 min soak
1 min water
```

The event delivers seven minutes of water while taking approximately 37 minutes
to complete.

## Required inputs

### Solar energy produced today

A cumulative energy sensor representing actual solar production since local
midnight. Supported units are Wh, kWh, and MWh. The source should normally reset
each day.

This value has two uses:

1. It contributes to the expected total solar production for the day.
2. Its 15-minute deltas form an observable two-hour history of recent solar
   production.

### Remaining solar production forecast

An energy sensor estimating how much additional solar energy will be produced
before the end of the current day. Supported units are Wh, kWh, and MWh.

The forecast is important in the morning. Actual production may still be low,
but a large remaining forecast allows the integration to allocate an appropriate
water budget before most of the day's sunlight has occurred.

### Irrigation switch or valve

The physical Home Assistant `switch` or `valve` that controls water delivery.
The config flow verifies that the entity exists, is available, and that its
start and stop services are registered.

Solar Irrigation confirms the reported entity state after every start and stop
command. The controller remains **Irrigating** until the physical entity is
confirmed inactive, and any actuator stop latency is included in delivered-time
accounting. It also monitors external state changes:

- an external stop ends the active event and accounts elapsed pump-on time;
- an unavailable actuator ends the event and reports an error;
- an actuator started outside Solar Irrigation, including during a soak period,
  is stopped for safety and reported as an error.

### Rain sensor, optional

A precipitation sensor in mm, cm, or inches. When omitted, the rain factor is
always 100 percent.

## Daily water-budget algorithm

### 1. Estimate total solar production

```text
expected solar today = actual solar today + remaining solar forecast
```

The integration exposes all three values separately:

- **Actual solar** is the normalized cumulative source measurement.
- **Remaining solar** is the normalized forecast still expected today.
- **Expected solar today** is their sum and is the value used to scale demand.

Keeping all three entities is intentional: it makes forecast changes and the
calculated total easy to inspect.

### 2. Calculate the solar factor

```text
solar factor = clamp(
    expected solar today / peak daily solar production,
    0,
    1
)
```

### 3. Calculate the rain factor

With no rain sensor:

```text
rain factor = 1
```

With a rain sensor:

```text
rain factor = clamp(
    1 - measured rain / rain skip threshold,
    0,
    1
)
```

Rain at or above the threshold makes the automatic budget zero.

### 4. Calculate today's pump-runtime budget

```text
daily water budget =
    peak daily water demand
    x solar factor
    x rain factor
```

The result is expressed in minutes of actual pump-on time for the current local
calendar day.

### 5. Subtract all confirmed delivery

Manual and automatic watering share the same delivery counter:

```text
remaining budget = max(
    0,
    daily water budget - delivered today
)
```

An explicit manual duration may intentionally exceed the current automatic
budget. Its confirmed pump-on time is still added to **Delivered today**, so
future automatic evaluations remain suppressed until the calculated budget is
larger than the accumulated delivery.

## Automatic scheduling every 15 minutes

Automatic irrigation is evaluated every 15 minutes while Home Assistant is
running.

The calculated daily budget is distributed across the configured watering
window. At each evaluation the integration calculates how much of the current
budget should be due by that point in the window. It uses one 15-minute lookahead
so the final scheduled evaluation can make the complete budget due before the
exclusive window end.

Conceptually:

```text
target delivered by now = daily budget x watering-window progress
new event amount = min(
    remaining daily budget,
    max(0, target delivered by now - delivered today)
)
```

Events below one minute are deferred to a later evaluation. This avoids very
short actuator operations.

If a watering or soak cycle is already active, the periodic evaluator does
nothing. No overlapping event can be scheduled. When the current event has
finished, the next 15-minute evaluation uses fresh data and decides whether more
water is due.

### Changes while an event is active

Before every new automatic pulse, the controller refreshes source data and
rechecks:

- the watering window;
- rain blocking;
- the latest daily budget;
- all delivery already accumulated today.

If a forecast revision, rain measurement, or manual delivery reduces the
remaining budget, later pulses are shortened or cancelled. If the budget grows,
the current event is not expanded beyond its original request; the next normal
15-minute evaluation schedules any additional amount that has become due.

## Watering window and night behavior

Default automatic window:

```text
05:00:00 to 22:00:00
```

Outside the window the controller reports **Sleeping** and does not start new
automatic pulses. A pulse already in progress is allowed to finish, but no new
pulse starts after the window has closed.

A window that crosses midnight is accepted, but a same-day daytime/evening
window is strongly recommended because delivery accounting resets at local
midnight. Equal start and end times are rejected.

Manual `run_now` actions are allowed outside the automatic window.

## Solar history

The cumulative actual-solar sensor is sampled at most once every 15 minutes.
Accepted deltas are retained for two hours and exposed through the **Solar
history** entity and downloaded diagnostics.

Available observations include:

- latest accepted delta;
- energy produced during the last hour;
- energy produced during the last two hours;
- average kWh/h during each window;
- a rolling kWh/h value weighted 70 percent toward the last hour and 30 percent
  toward the full two-hour window;
- timestamp, cumulative value, delta, elapsed time, and normalized rate for every
  retained sample.

A delayed reading is not discarded. The cumulative delta remains valid, so the
integration stores it with its actual elapsed interval. Rolling calculations
include only the proportional part of that interval overlapping the requested
one-hour or two-hour window. This avoids both losing valid energy and treating a
multi-hour accumulated delta as an instantaneous spike.

After first setup, restart, or a detected daily reset, the current cumulative
value is represented as one coarse interval beginning at local midnight. The
total energy is exact, while its distribution inside that interval is an average
estimate. Normal 15-minute samples replace the coarse interval as the two-hour
window advances. A negative delta never enters the algorithm.

The **Solar history** entity state is the number of retained samples. There is no
separate sample-count entity. In version 2.5 the history is an observability and
tuning input; it does not independently add water beyond the daily budget derived
from actual production plus the remaining-production forecast. The 15-minute
evaluator still reacts to every updated budget and delivery total.

## Configuration parameters

### Peak daily solar production

- Unit: kWh/day
- Range: 0.001 to 10,000
- Default: 65
- Location: integration configuration/options

A fixed calibration for the photovoltaic system and forecast source. It
represents a strong or peak production day. It normally changes only when the PV
system or forecast method changes.

### Peak daily water demand

- Unit: minutes/day
- Range: 10 to 240
- Step: 1 minute
- Default: 60
- Location: writable Home Assistant `number` entity

The total pump-on time that the crops and irrigation circuit would need on a peak
solar day with no rain. It is both a seasonal crop-demand scale and the maximum
automatic daily budget before solar and rain factors are applied.

Adjust it as plants mature, fruit, or decline during the season. Updating the
number refreshes calculations in place and does not reload or interrupt an active
event. An automatic event rechecks the new budget before its next pulse.

### Rain amount that skips irrigation

- Unit: mm
- Range: 0.1 to 1,000
- Default: 5

The rain amount at which the automatic rain factor reaches zero. Half the
threshold produces approximately a 50 percent rain factor.

### Maximum pulse duration

- Writable `number` entity
- Unit: minutes
- Range: 0.5 to 15
- Step: 0.5
- Default: 3

The longest continuous pump-on period within one event. It can be adjusted from
a dashboard or automation without reloading the integration. A pulse already in
progress keeps its planned duration; the new value applies to the next pulse.

### Soak duration

- Writable `number` entity
- Unit: minutes
- Range: 1 to 30
- Step: 1
- Default: 15

The pump-off interval after each non-final pulse. It can be adjusted without an
integration reload. A soak already in progress keeps its scheduled deadline; the
new value applies to the next soak. During soaking the controller reports
**Soaking** and no other event can start.

### Calculation update interval

- Unit: seconds
- Range: 60 to 86,400
- Default: 3,600

The requested coordinator interval. Solar Irrigation internally refreshes at
least every 15 minutes because the automatic evaluator and solar-history sampler
need current values. Shorter refreshes do not create extra history samples until
the minimum sampling interval has elapsed.

### Automatic watering window start/end

- Defaults: 05:00:00 and 22:00:00

The inclusive start and exclusive end of automatic watering. Manual actions are
not restricted by this window.

## Manual actions

Actions use a Home Assistant configuration-entry selector, so the Solar
Irrigation instance can be chosen from a dropdown rather than by copying an entry
ID. Existing YAML using the legacy `entry_id` field remains accepted for backward
compatibility, but new automations should use `config_entry_id`.

### `solar_irrigation.run_now`

Fields:

- **Configuration entry**: the Solar Irrigation instance.
- **Duration**, optional: total pump-on minutes for this event. The duration is
  still divided into configured pulses and soak periods.
- **Ignore rain**: bypass both rain blocking and rain-based runtime reduction.

Behavior without an explicit duration:

- normal mode uses the current remaining rain-adjusted budget;
- Ignore rain reads the actual and remaining solar inputs directly and uses the
  current dry, solar-scaled remaining budget;
- a configured rain sensor may be unavailable without blocking this dry override;
- with no rain sensor, Ignore rain is harmless and produces the same dry budget.

An explicit duration is an operator override. Confirmed delivery accumulates in
the daily total and therefore influences later automatic decisions.

### `solar_irrigation.stop`

Stops both a running pulse and a pending soak interval. During a pulse the
actuator is stopped and elapsed delivery is accounted. During soaking the pump is
already off and the next pulse is cancelled.

## Daily reset and persistence

At the first evaluation or startup detected on a new Home Assistant local date:

- delivered runtime resets to zero;
- pulse count resets to zero;
- the current daily budget is recalculated from fresh sources.

Unused budget is never carried into the next day.

Controller state and solar history are stored per config entry. Physical
actuator recovery and monitoring start before the first source refresh, so a
source outage during setup cannot bypass the pump-off safety check. If Home
Assistant restarts during a pulse, an actuator that is still active is stopped and
counted through the confirmed physical stop, including time beyond the requested
pulse. If the actuator is already inactive, recovery is conservatively capped at
the planned pulse end because the exact earlier off time is unavailable. A
persisted stop failure keeps the active timing and is counted through later
confirmed recovery. The event result is marked **Interrupted**. Requested event
duration and actual delivered duration are stored separately.

## Controller states

- **Initializing**: persisted state is loading.
- **Waiting for solar history**: no accepted delta sample exists and less than one
  minute is currently due.
- **Sleeping**: outside the automatic watering window.
- **Monitoring**: no event is active.
- **Waiting for pulse**: inside the window, but less than one minute is due or an
  event has just been scheduled.
- **Irrigating**: the physical actuator is confirmed active.
- **Soaking**: the actuator is off between event pulses.
- **Paused by rain**: rain currently blocks more automatic delivery.
- **Daily budget reached**: delivered time is at or above the current budget.
- **Error**: a source refresh, actuator start, actuator stop, or safety
  reconciliation failed.

Actuator errors remain visible until a later successful watering operation proves
recovery. Source-data errors clear after a successful source refresh. The status
entity includes the human-readable error message as an attribute.

## Observability

The integration exposes:

- actual, remaining, and expected solar energy;
- solar factor and optional rain factor;
- current daily water budget;
- delivered and remaining minutes today;
- confirmed pulse count today;
- controller status and decision reason;
- requested and actual duration of the latest event;
- active pulse start/end and next-pulse time;
- the physical actuator state and whether it currently reports active flow;
- maximum pulse and soak settings;
- complete rolling solar history;
- the latest error message.

Controller-backed entities subscribe to controller callbacks and write their
state immediately. They do not wait for a normal polling interval when a pulse
starts, ends, begins soaking, is stopped externally, or enters an error state.

## Installation

1. Install the repository through HACS as a custom integration, or copy
   `custom_components/solar_irrigation` into Home Assistant's
   `custom_components` directory.
2. Restart Home Assistant.
3. Open **Settings -> Devices & services -> Add integration**.
4. Select **Solar Irrigation** and configure the inputs.

## Development

Create the test environment:

```bash
make setup_test_env
```

Run behavioral tests:

```bash
make test-unit
```

Run branch coverage enforcement:

```bash
make test-coverage
```

Run Ruff:

```bash
make lint
```

Run the complete release quality gate, including Hassfest:

```bash
make quality
```

The strict local target is 85 percent branch coverage. Tests focus on the
physical actuator state machine, run-soak sequencing, budget enforcement,
configuration validation, delayed solar samples, restart recovery, immediate
observability, diagnostics, and Home Assistant action behavior.



### 2.6.0 live pulse tuning

Version 2.6 exposes **Maximum pulse duration** and **Soak duration** as writable
Home Assistant number entities. Values are persisted per config entry and are
refreshed without reloading the integration. Maximum pulse duration supports
0.5-15 minutes in 0.5-minute steps; soak duration supports 1-30 minutes in
one-minute steps. Active stages are not rescheduled: changes apply to the next
pulse or soak.

### 2.5.2 test and race-condition hotfix

Version 2.5.2 defers the first pulse by one event-loop checkpoint so an
immediate stop request cannot race with actuator activation. It also fixes
orphaned-pulse finalization after a failed stop and cleans up controller sensor
listeners correctly in the Home Assistant test suite.

## Upgrade notes for 2.5

- Automatic delivery now uses true pulse-and-soak events.
- Automatic evaluation occurs every 15 minutes and may schedule multiple events
  per day, while never overlapping an active run or soak cycle.
- Manual and automatic delivery share one daily counter.
- Remaining daily budget is enforced before an event and before every automatic
  pulse.
- `ignore_rain` now works with calculated duration, with no rain sensor, and
  when a configured rain sensor is unavailable.
- Actuator start/stop state is confirmed, external state changes are reconciled,
  and controller status remains Irrigating until physical stop is confirmed.
- Manual actions use `config_entry_id` selectors; legacy `entry_id` YAML remains
  accepted.
- Maximum pulse and soak duration options were added.
- Controller status entities are push-updated.
- Delayed solar samples are proportionally represented in rolling windows, and
  first/restart samples preserve the cumulative value measured since midnight.
- Config-entry schema version 3 clamps legacy peak-demand values to the supported
  10-240 minute range and adds pulse-and-soak defaults.
