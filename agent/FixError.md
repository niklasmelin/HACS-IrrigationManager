# Solar Irrigation Integration Recovery Plan

## Objective

Bring the integration into compliance with Home Assistant's Config Entry
architecture and make it production-ready.

## Phase 1 -- Restore Initialization (Highest Priority)

### Task 1: Create the DataUpdateCoordinator

-   Instantiate `SolarIrrigationCoordinator` in `async_setup_entry()`.
-   Call `await coordinator.async_config_entry_first_refresh()`.
-   Abort setup cleanly if the first refresh fails.

**Acceptance** - Coordinator starts. - Initial sensor values are
available.

### Task 2: Store coordinator

Store:

``` python
hass.data.setdefault(DOMAIN, {})
hass.data[DOMAIN][entry.entry_id] = coordinator
```

Never store a single global coordinator.

### Task 3: Entity access

Update every entity platform to retrieve the coordinator using
`hass.data[DOMAIN][entry.entry_id]`.

## Phase 2 -- Entity Lifecycle

### Task 4: Verify platform forwarding

Ensure:

``` python
PLATFORMS=["sensor","switch"]
await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
```

### Task 5: Correct unload

Unload platforms first, then remove only:

``` python
hass.data[DOMAIN].pop(entry.entry_id)
```

Do not remove the entire domain.

## Phase 3 -- Services

### Task 6

Register services in Python:

-   solar_irrigation.run_now
-   solar_irrigation.stop

Keep `services.yaml` as documentation only.

## Phase 4 -- Coordinator Responsibilities

Move all business logic into the coordinator:

-   Read configured sensors
-   Validate numeric values
-   Calculate expected solar
-   Calculate scale factor
-   Calculate irrigation runtime
-   Publish coordinator data

Entities must only display coordinator state.

## Phase 5 -- Irrigation Controller

Create a dedicated controller responsible for:

-   Daily scheduling
-   Pump on/off
-   Runtime timer
-   Last execution persistence
-   Restart recovery

Avoid embedding this logic in sensor entities.

## Phase 6 -- Robustness

Handle:

-   unavailable
-   unknown
-   non-numeric
-   negative values
-   unavailable switch

Log meaningful errors and skip irrigation safely.

## Phase 7 -- Testing

Functional tests:

1.  Config Flow
2.  Coordinator startup
3.  Entity creation
4.  Runtime calculation
5.  Manual services
6.  Daily schedule
7.  Restart recovery
8.  Unload/reload
9.  Invalid sensors
10. Multiple config entries

## Definition of Done

-   Integration installs via HACS.
-   Config Flow completes successfully.
-   Coordinator refreshes correctly.
-   Entities are created.
-   Services work.
-   Irrigation executes once per day.
-   Restart recovery works.
-   Clean unload/reload.
-   No Home Assistant startup exceptions.
-   Passes Home Assistant quality checks.