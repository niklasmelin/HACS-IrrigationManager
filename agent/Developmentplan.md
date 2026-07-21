# Hermes Development Plan: Solar Irrigation Manager

**Audit date:** 2026-07-21  
**Repository snapshot:** `HACS-IrrigationManager-main.zip` supplied by the user  
**Integration domain:** `solar_irrigation`  
**Primary specification:** `IrrigationManager.md`  
**Most recent recovery notes:** `FixError.md`

---

## 1. Mission

Continue development of the supplied Home Assistant custom integration until it is a safe, testable, HACS-installable component that:

1. Is configured exclusively through a Home Assistant config flow.
2. Reads actual solar energy produced today and forecast remaining solar energy today.
3. Converts both values to kWh, validates them, and calculates:
   - expected solar today;
   - scale factor from 0.0 to 1.0;
   - irrigation runtime in minutes and seconds.
4. Runs one configured irrigation switch once per local calendar day at 06:00.
5. Recovers correctly after Home Assistant restarts.
6. Provides functional `solar_irrigation.run_now` and `solar_irrigation.stop` actions.
7. Exposes diagnostic sensor entities.
8. Supports multiple config entries without data leakage or cross-control.
9. Unloads and reloads cleanly.
10. Has automated tests and repository validation that prove the above.

Do not treat syntax compilation, file existence, or version-number changes as proof of functionality.

---

## 2. Audit Scope and Limitations

The supplied archive was inspected statically. All Python files compile and all JSON files parse, but there is no included Home Assistant test environment and no tests. Therefore, compilation success proves only Python syntax; it does not prove that Home Assistant can load the integration.

The audit included:

- every repository file;
- `IrrigationManager.md`;
- `FixError.md`;
- `session.md`;
- Python compilation;
- JSON parsing;
- comparison with current Home Assistant and HACS developer guidance as of July 2026.

---

## 3. Executive Verdict

**Current state: non-functional scaffold with partial calculation logic.**

The archive is not ready for HACS distribution and should not be installed on a production Home Assistant instance. The most important reason is that the sensor and switch platforms cannot be set up correctly: their `async_setup_entry` functions have the wrong signature and never call `async_add_entities`. Even if that is fixed, the actions are placeholders with invalid service-handler signatures, the irrigation controller is not connected to setup, and scheduling, persistence, restart recovery, cancellation, and safety handling are absent.

The `README.md` statement that final verification passed is unsupported by the code and validation script.

---

## 4. Current-State Findings

### 4.1 P0 startup and functional blockers

#### P0-1: Entity platform setup is invalid

Files:

- `custom_components/solar_irrigation/sensor.py:23`
- `custom_components/solar_irrigation/switch.py:15`

Both currently define setup with two arguments and return `True`. A config-entry entity platform must accept the entity-adder callback and add entities. The current functions neither accept `async_add_entities` nor create any entities.

Expected shape:

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([...])
```

Impact:

- platform forwarding is expected to fail with a setup exception;
- no diagnostic sensors are created;
- no custom switch is created;
- setup may abort before actions are registered.

#### P0-2: The coordinator is not initialized using the current explicit config-entry pattern

Files:

- `custom_components/solar_irrigation/__init__.py:33`
- `custom_components/solar_irrigation/coordinator.py:16`

The coordinator receives only `hass` and an interval. It accesses `self.config_entry` later but does not pass `config_entry=entry` to `DataUpdateCoordinator`. This relies on implicit context behavior and is not acceptable for the stated 2026 target. Pass the config entry explicitly.

The update routine also returns an `{"error": ...}` dictionary on invalid input. That marks the coordinator refresh as successful even though its data is unusable. Invalid source data should raise `UpdateFailed` so `last_update_success` is false and entities become unavailable.

#### P0-3: Registered actions cannot execute

File: `custom_components/solar_irrigation/__init__.py:16-26,45-56`

Problems:

- handlers are placeholders;
- handler signatures accept `(hass, data)`, while Home Assistant passes a `ServiceCall` to an ordinary registered handler;
- no schema is supplied;
- no config entry or controller is resolved;
- no pump is controlled;
- actions are registered once per config entry, causing collisions or overwrites;
- actions are not cleanly removed or managed as shared integration resources.

#### P0-4: The irrigation controller is disconnected and incomplete

File: `custom_components/solar_irrigation/irrigation.py`

Problems:

- it is never instantiated;
- it is never stored in runtime data;
- no setup or shutdown method exists;
- `from homeassistant.helpers.storage import Storage` is wrong; the public helper is `Store`;
- `asyncio.sleep(runtime_seconds)` creates a long-lived service coroutine rather than a recoverable Home Assistant timer;
- stop does not cancel a pending sleep/task;
- no lock prevents overlapping runs;
- no once-per-day guard exists;
- no schedule exists;
- no storage exists despite the placeholder comment;
- no restart recovery exists;
- no verification that the switch actually became on/off exists;
- failure paths do not guarantee pump shutdown.

#### P0-5: The required daily behavior is absent

The specification requires:

- run at 06:00 local time;
- if Home Assistant starts after 06:00 and watering has not run, run immediately;
- never run more than once that day;
- persist the last execution date.

None of this exists.

---

### 4.2 P1 correctness and safety defects

#### P1-1: Division by zero is allowed

`config_flow.py` accepts `max_solar = 0`, while `coordinator.py` divides by `max_solar`. Require a value greater than zero.

#### P1-2: Negative source sensor values are not rejected

The specification says negative values are invalid and irrigation must not start. Current code adds negative values and merely clamps the final scale. Reject each negative source value before calculation.

#### P1-3: Energy units are assumed, not validated or converted

The configuration says kWh, but the code converts only the numeric state and ignores the unit attribute. A Wh source would be treated as kWh. Convert supported Home Assistant energy units to kWh or reject unsupported/missing units with a clear error.

#### P1-4: Pump availability and domain are not checked at execution time

The selected entity may be removed, unavailable, unknown, or no longer be a switch. Never energize a pump unless its current state is valid and the entity resolves to the switch domain.

#### P1-5: Long-running execution lacks cancellation and shutdown guarantees

Unload, reload, manual stop, and Home Assistant shutdown must cancel scheduled callbacks and active runs. The pump must be turned off in a guarded cleanup path.

#### P1-6: Runtime zero behavior is undefined

A calculated duration of zero must be a safe no-op. It must not pulse the pump on and immediately off. Record a completed/no-water execution for the day without calling `switch.turn_on`.

#### P1-7: Multiple config entries are unsafe

`async_unload_entry` removes the entire domain using `hass.data.pop(DOMAIN, None)`. Unloading one entry would delete all entries. Current action handling also has no way to select an integration instance.

---

### 4.3 Entity API and platform defects

Files: `sensor.py`, `switch.py`

Problems:

- sensor classes inherit only `CoordinatorEntity`, not `SensorEntity`;
- the legacy `state` and `unit_of_measurement` properties are used instead of `native_value` and `native_unit_of_measurement`;
- imported `SensorEntity`, `SwitchEntity`, and `Entity` are unused;
- no device classes are set;
- no state classes or enum options are defined where appropriate;
- no `has_entity_name` behavior;
- no translation keys;
- unique IDs are not namespaced by config entry, so multiple entries would collide;
- availability does not follow `coordinator.last_update_success`;
- `Last Irrigation` is declared in constants/specification but no entity is implemented;
- the switch methods are synchronous placeholders and do nothing;
- coordinator data never contains `switch_on`, so the custom switch would remain off even if added.

**Recommended decision:** remove the custom `switch.py` platform from the first functional release. The integration already controls a user-selected external switch; a second proxy switch has no clearly specified behavior and increases risk. Keep only the sensor platform and two actions. Add a custom enable/disable switch later only after defining its semantics and tests.

---

### 4.4 Config-flow defects

File: `config_flow.py`

Problems:

- old `FlowResult` typing is used instead of current `ConfigFlowResult`;
- `HomeAssistant` is imported but unused;
- no duplicate prevention exists;
- selecting the same pump in multiple entries is possible;
- no validation that source entities represent energy;
- no value/unit validation at submission time where states are available;
- tunable settings are mixed with identity/source configuration;
- no options flow or reconfigure flow;
- no update listener reloads the entry after option changes;
- `max_solar` permits zero;
- labels exist, but descriptions and errors are incomplete.

Recommended configuration model:

- `entry.data`: source sensor entity IDs and irrigation switch entity ID;
- `entry.options`: maximum solar, maximum runtime, update interval;
- unique ID: the selected irrigation entity ID, preventing duplicate control of the same pump.

For the first passing milestone it is acceptable to keep all values in `entry.data`, but add an options flow before release.

---

### 4.5 Metadata, localization, documentation, and packaging defects

#### `hacs.json`

Current root metadata contains unsupported integration-manifest keys:

- `description`;
- `documentation`;
- `categories`;
- `version`;
- `codeowners`;
- `config_flow`.

HACS versioning must not be managed in `hacs.json`. The integration version belongs in `custom_components/solar_irrigation/manifest.json` and in GitHub tags/releases.

Recommended minimal root file:

```json
{
  "name": "Solar Irrigation",
  "content_in_root": false,
  "country": "SE",
  "homeassistant": "<tested minimum version>"
}
```

Do not choose the minimum Home Assistant version until tests pass against it.

#### `manifest.json`

Problems:

- missing `issue_tracker`, which current HACS integration requirements expect;
- missing explicit `integration_type`;
- `iot_class` is incorrectly `local_push`; this integration calculates from other Home Assistant states, so `calculated` is appropriate;
- `dependencies: ["sensor", "switch"]` is unnecessary;
- version policy is inconsistent across files and session history.

Recommended target fields:

```json
{
  "domain": "solar_irrigation",
  "name": "Solar Irrigation",
  "codeowners": ["@niklasmelin"],
  "config_flow": true,
  "documentation": "https://github.com/niklasmelin/HACS-IrrigationManager",
  "integration_type": "service",
  "iot_class": "calculated",
  "issue_tracker": "https://github.com/niklasmelin/HACS-IrrigationManager/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

Use `0.1.0` only when creating a clean first functional release, or retain the existing version until release. Do not bump versions during intermediate fixes.

#### `services.yaml`

The file incorrectly has a top-level `services:` key. Action names must be at the root. It also lacks current selectors and translations.

#### Localization

- `strings.json` is missing;
- entity translations use strings directly instead of objects with `name` keys;
- no translated action fields, errors, abort reasons, enum states, or data descriptions;
- `translations/en.json` must mirror `strings.json` for a custom integration.

#### Repository

Missing or inadequate:

- `LICENSE`;
- brand assets (`brand/icon.png` at minimum for current HACS publishing requirements);
- meaningful README;
- tests;
- CI workflows;
- development configuration;
- `.gitignore`;
- release notes/changelog strategy.

Committed `__pycache__` files must be deleted and ignored.

---

## 5. `FixError.md` Compliance Matrix

| Recovery task | Current result | Assessment |
|---|---|---|
| Instantiate coordinator | Present | Partial; config entry is not explicitly passed and refresh error handling is wrong |
| First refresh | Present | Partial; invalid input returns a successful error dictionary |
| Store per entry | Present in `hass.data` | Partial; current best practice is typed `entry.runtime_data` |
| Entity access | Not implemented | Fail; platforms add no entities |
| Platform forwarding | Present | Partial; forwarded platform setup is invalid |
| Correct unload | Incorrect | Fail; entire domain is removed and unload result is ignored |
| Register actions in Python | Present as placeholders | Fail; invalid handlers and no behavior |
| Coordinator business logic | Basic arithmetic present | Partial; unit handling, error semantics, typing, and safety missing |
| Dedicated controller | File exists | Fail; unused and lacks scheduling/persistence/recovery |
| Robust invalid-state handling | Partial | Fail; negative values and switch failures are not handled safely |
| Functional tests | None | Fail |
| HACS installable | Unproven | Fail |
| Once-per-day execution | Absent | Fail |
| Restart recovery | Absent | Fail |
| Clean unload/reload | Incorrect | Fail |
| Quality checks | Not present | Fail |

---

## 6. Mandatory Hermes Operating Contract

Hermes must follow these rules for every phase.

### 6.1 Work discipline

1. Work on exactly one phase at a time.
2. Read every affected file before editing it.
3. Create or update tests in the same phase as behavior changes.
4. Run the phase's validation commands before claiming completion.
5. Do not move to the next phase while any new test, lint, type, HACS, hassfest, or runtime error remains.
6. Never replace a failing test with a weaker test merely to make it pass.
7. Never remove error handling to silence a test.
8. Never use placeholder comments such as “implementation would go here.”
9. Never claim a file is implemented merely because it exists.
10. Never claim Home Assistant compatibility based only on `py_compile` or `compileall`.

### 6.2 Version discipline

1. Do not edit the integration version during phases 0-10.
2. Do not put a version in `hacs.json`.
3. Change `manifest.json` version exactly once, at the release phase.
4. The release tag and manifest version must match.
5. A version bump is not a development milestone or proof of correctness.

### 6.3 Completion report required after each phase

Hermes must output:

- phase number and name;
- files changed;
- concise behavioral change summary;
- exact commands run;
- pass/fail result for every command;
- tests added and what each proves;
- unresolved issues;
- `git diff --stat`;
- no “ready for release” statement unless phase 11 release gates all pass.

### 6.4 Stop conditions

Hermes must stop and repair the current phase when any of the following occurs:

- Home Assistant setup exception;
- platform forwarding error;
- action handler exception;
- pump can remain on after cancellation/error;
- duplicate daily run is possible;
- multiple entries interfere;
- unload leaves listeners or timers active;
- test relies on real sleeping;
- test outcome depends on local wall-clock time;
- HACS Action or hassfest fails;
- README claims behavior not proven by tests.

---

## 7. Target Architecture

### 7.1 Repository layout

```text
custom_components/
  solar_irrigation/
    __init__.py
    config_flow.py
    const.py
    coordinator.py
    diagnostics.py
    irrigation.py
    manifest.json
    sensor.py
    services.yaml
    strings.json
    translations/
      en.json
    brand/
      icon.png

tests/
  __init__.py
  conftest.py
  test_config_flow.py
  test_coordinator.py
  test_diagnostics.py
  test_init.py
  test_irrigation.py
  test_sensor.py
  test_services.py

.github/
  workflows/
    hacs.yml
    hassfest.yml
    tests.yml

.gitignore
LICENSE
README.md
hacs.json
pyproject.toml
requirements_test.txt
```

Remove `switch.py` for the first release unless a specific, tested purpose is approved.

### 7.2 Runtime object model

Use typed config-entry runtime data rather than a nested global dictionary.

```python
@dataclass(slots=True)
class SolarIrrigationRuntimeData:
    coordinator: SolarIrrigationCoordinator
    controller: SolarIrrigationController

SolarIrrigationConfigEntry = ConfigEntry[SolarIrrigationRuntimeData]
```

Assign it in setup:

```python
entry.runtime_data = SolarIrrigationRuntimeData(
    coordinator=coordinator,
    controller=controller,
)
```

Benefits:

- automatic config-entry lifetime;
- no cross-entry key mistakes;
- simpler platform access;
- better type checking;
- no manual `hass.data` removal.

### 7.3 Coordinator data model

Use an immutable dataclass or typed dictionary, preferably a frozen dataclass.

Suggested fields:

```text
actual_solar_kwh: float
remaining_solar_kwh: float
expected_solar_kwh: float
scale_factor: float
runtime_minutes: float
runtime_seconds: int
calculated_at: datetime
```

Controller state must not be faked as a constant `idle` field in each refresh. The controller should own:

```text
status: idle | scheduled | running | completed | error
last_execution: datetime | None
active_started_at: datetime | None
active_end_at: datetime | None
last_error: str | None
```

When controller state changes, notify sensor listeners through the coordinator or a dedicated callback mechanism.

### 7.4 Execution state machine

Allowed transitions:

```text
idle -> scheduled
scheduled -> running
scheduled -> idle            # schedule cancelled/unloaded
running -> completed
running -> error             # pump or timer failure, after forced shutdown
running -> completed         # manual stop after a successful start
completed -> scheduled       # next local day
error -> scheduled           # next local day or explicit retry
```

Never permit two simultaneous `running` operations for one entry.

---

## 8. Detailed Implementation Phases

# Phase 0 — Establish a trustworthy baseline

## Objective

Stop version churn, remove misleading generated artifacts, and create a development environment capable of running Home Assistant behavior tests.

## Tasks

1. Create a new development branch, for example `fix/functional-integration`.
2. Save the supplied state as a baseline commit if it is not already in version control.
3. Remove all `__pycache__` directories and `.pyc` files.
4. Add `.gitignore` entries for Python caches, virtual environments, pytest cache, coverage files, IDE files, and build artifacts.
5. Remove or rewrite `validate_integration.py`; it currently:
   - hard-codes `~/Development/Irrigation`;
   - looks for root `hacs.json` inside the component directory;
   - ignores shell exit codes from `os.system`;
   - reports compilation as success even when behavior is untested.
6. Add a current test environment using `pytest-homeassistant-custom-component` pinned to the chosen Home Assistant version.
7. Add `pyproject.toml` configuration for pytest, Ruff, and coverage.
8. Do not edit any version field.

## Required baseline commands

```bash
python -m compileall custom_components/solar_irrigation
python -m pytest --collect-only
ruff check .
ruff format --check .
```

At this phase, pytest collection may initially reveal missing tests, but the environment itself must start correctly.

## Acceptance criteria

- no cache files are tracked;
- tests can be collected;
- Ruff can analyze the repository;
- validation commands use repository-relative paths;
- no version changed;
- baseline findings are recorded in an issue or `DEVELOPMENT.md`.

## Suggested commit

`chore: establish integration development baseline`

---

# Phase 1 — Correct metadata and repository structure

## Objective

Make the repository structurally valid before implementing runtime behavior.

## Tasks

1. Replace `hacs.json` with supported HACS keys only.
2. Update `manifest.json`:
   - add `issue_tracker`;
   - add `integration_type: service`;
   - change `iot_class` to `calculated`;
   - remove unnecessary `dependencies` or set to an empty list;
   - retain the current version unchanged for now.
3. Add `LICENSE` with an explicitly chosen license.
4. Add `strings.json` and make `translations/en.json` mirror it.
5. Fix `services.yaml` root structure, even though action behavior will be implemented later.
6. Delete `switch.py` and remove `switch` from platform forwarding unless the user explicitly requires a proxy switch.
7. Add a temporary minimal README that clearly says development is in progress; remove all unsupported “passed” claims.
8. Add `brand/icon.png` before HACS publishing. Do not create a misleading brand asset without user approval; use a simple original icon.

## Acceptance criteria

- JSON/YAML parse;
- HACS Action accepts metadata or reports only expected unpublished-release conditions;
- hassfest accepts manifest and translations;
- no unsupported `hacs.json` keys;
- README no longer claims functionality not present;
- the manifest version was not bumped.

## Suggested commit

`chore: correct HACS and Home Assistant metadata`

---

# Phase 2 — Rebuild constants, types, and runtime data

## Objective

Create one typed source of truth for configuration, states, and config-entry runtime objects.

## Tasks

1. Rewrite `const.py`:
   - use `DOMAIN` everywhere instead of literal strings;
   - use Home Assistant constants for units;
   - define defaults in one place;
   - define minimum/maximum limits;
   - define action names;
   - define a `StrEnum` for controller status;
   - remove unused constants.
2. Add typed models, either in `models.py` or `__init__.py`:
   - calculation dataclass;
   - persisted storage dataclass/serialization shape;
   - runtime-data dataclass;
   - typed config-entry alias.
3. Define storage constants:
   - storage version;
   - key must include `entry.entry_id` to isolate entries.
4. Define execution limits:
   - `max_solar > 0`;
   - `max_runtime >= 0`;
   - manual override bounded to a documented safe maximum;
   - update interval bounded to a reasonable range.

## Acceptance criteria

- strict type annotations on new code;
- no mutable module-level state;
- tests cover enum values and serialization defaults;
- all modules import constants rather than duplicating string keys.

## Suggested commit

`refactor: add typed solar irrigation runtime models`

---

# Phase 3 — Rebuild the config flow

## Objective

Create valid, user-friendly, duplicate-safe configuration.

## Required behavior

The flow must collect:

- actual solar energy today sensor;
- remaining solar energy today sensor;
- irrigation pump switch;
- maximum daily solar in kWh;
- maximum runtime in minutes;
- update interval.

## Tasks

1. Use `ConfigFlowResult` and the `DOMAIN` constant.
2. Use entity selectors:
   - source entities restricted to `sensor`;
   - pump restricted to `switch`;
   - where supported, filter source sensors by energy device class.
3. Use number selectors rather than bare Voluptuous coercion for numeric user experience.
4. Require `max_solar` to be greater than zero.
5. Decide whether zero runtime is allowed:
   - recommended: allow zero as a deliberate disable/no-water configuration;
   - controller must then perform a no-op without switching the pump.
6. Set config-entry unique ID to the selected pump entity ID.
7. Abort duplicate setup if that pump already has an entry.
8. Derive a readable entry title from the pump entity name, falling back to entity ID.
9. Validate available source states during setup without requiring them to be online forever:
   - numeric state when available;
   - non-negative;
   - recognized energy unit;
   - produce translated field errors.
10. Add an options flow for maximum solar, maximum runtime, and update interval.
11. Add an update listener that reloads the config entry after options changes.
12. Add a reconfigure step later if source entity IDs must be editable.
13. Update `strings.json` and `translations/en.json` with:
   - titles;
   - field names;
   - field descriptions;
   - validation errors;
   - duplicate abort reason;
   - options flow strings.

## Tests

Create `tests/test_config_flow.py` covering:

1. form display;
2. successful entry creation;
3. defaults;
4. duplicate pump abort;
5. zero maximum solar rejection;
6. negative values rejection;
7. invalid source state;
8. invalid/missing source unit;
9. unavailable source allowed or rejected according to documented policy;
10. options flow updates and triggers reload;
11. correct title and unique ID.

## Acceptance criteria

- every branch has a test;
- config-flow coverage is effectively complete;
- no duplicate pump can be configured;
- invalid divisor cannot reach runtime code;
- errors are translated, not hard-coded UI strings.

## Suggested commit

`feat: implement validated solar irrigation config flow`

---

# Phase 4 — Implement the calculation coordinator correctly

## Objective

Make calculation data reliable, typed, unit-safe, and unavailable on invalid input.

## Tasks

1. Change coordinator constructor to accept the typed config entry.
2. Pass `config_entry=entry` explicitly to `DataUpdateCoordinator`.
3. Set an update interval from `entry.options` with fallback to `entry.data` and defaults.
4. Read source entity IDs from the config entry.
5. Implement a helper that:
   - gets the Home Assistant state;
   - rejects missing entity;
   - rejects `unknown` and `unavailable`;
   - parses numeric values;
   - rejects NaN and infinity;
   - rejects negative values;
   - reads the unit attribute;
   - converts Wh, kWh, and MWh to kWh using Home Assistant unit helpers;
   - rejects incompatible units.
6. Calculate exactly:

```text
expected_kwh = actual_kwh + remaining_kwh
scale_factor = clamp(expected_kwh / max_solar_kwh, 0.0, 1.0)
runtime_minutes = scale_factor * max_runtime_minutes
runtime_seconds = round(runtime_minutes * 60)
```

7. Do not round intermediate values except for presentation.
8. Return a typed calculation object.
9. Raise `UpdateFailed` for invalid source data.
10. Log useful context once through coordinator failure handling; avoid repetitive error spam.
11. Add a public `async_refresh_before_run()` helper only if it improves clarity; otherwise call `async_request_refresh`/`async_refresh` from the controller before execution.

## Tests

Create `tests/test_coordinator.py` covering:

1. specification example;
2. zero solar;
3. exact maximum solar;
4. above maximum clamps to 1.0;
5. fractional runtime rounds to nearest second;
6. Wh conversion;
7. kWh conversion;
8. MWh conversion;
9. missing entity;
10. unknown state;
11. unavailable state;
12. non-numeric state;
13. negative actual;
14. negative remaining;
15. NaN;
16. infinity;
17. missing unit;
18. incompatible unit;
19. max solar defensive zero check;
20. coordinator `last_update_success` false on error.

## Acceptance criteria

- calculation tests match `IrrigationManager.md`;
- invalid data never returns a successful error dictionary;
- the coordinator is passed its config entry explicitly;
- all values are normalized to kWh;
- no controller logic is embedded in sensor entities.

## Suggested commit

`feat: implement validated irrigation calculations`

---

# Phase 5 — Implement config-entry setup and unload

## Objective

Create and own the coordinator/controller lifecycle correctly.

## Setup sequence

1. Construct coordinator with explicit entry.
2. Run `await coordinator.async_config_entry_first_refresh()`.
3. Construct controller.
4. Run `await controller.async_setup()` to load storage and create schedules.
5. Assign typed `entry.runtime_data`.
6. Forward the sensor platform and await it.
7. Register the options-update listener with `entry.async_on_unload`.

If controller setup fails after it has allocated resources, clean them before re-raising.

## Unload sequence

1. Unload forwarded platforms.
2. Only if platform unload succeeds, call `await controller.async_shutdown()`.
3. Shutdown must:
   - cancel daily schedule callbacks;
   - cancel end-of-run timer callbacks;
   - prevent new runs;
   - turn off the pump if this integration has an active run;
   - clear listeners.
4. Return the platform unload result.
5. Do not remove the whole integration domain from `hass.data`.

## Tests

Create `tests/test_init.py` covering:

1. successful setup;
2. first coordinator refresh failure produces setup retry/not-ready behavior;
3. sensor platform forwarding;
4. runtime data contains coordinator and controller;
5. unload success;
6. unload failure leaves runtime resources intact or handles them according to HA lifecycle;
7. reload;
8. two config entries setup and unload independently;
9. no listeners/timers remain after unload.

## Acceptance criteria

- no global single coordinator;
- no cross-entry data deletion;
- first refresh failure is represented by Home Assistant setup state, not fake coordinator data;
- unload/reload is repeatable.

## Suggested commit

`feat: implement config entry runtime lifecycle`

---

# Phase 6 — Implement diagnostic sensors

## Objective

Expose calculation and controller state using current Home Assistant entity APIs.

## Entities

1. Expected Solar Today
   - `SensorDeviceClass.ENERGY`;
   - native unit kWh;
   - no misleading monotonic state class;
   - suggested precision appropriate to source data.
2. Solar Scale Factor
   - numeric 0.0-1.0;
   - no unit;
   - suggested precision 3.
3. Irrigation Runtime
   - `SensorDeviceClass.DURATION`;
   - native unit minutes.
4. Irrigation Runtime Seconds
   - `SensorDeviceClass.DURATION`;
   - native unit seconds.
5. Irrigation Status
   - `SensorDeviceClass.ENUM`;
   - translated options: idle, scheduled, running, completed, error.
6. Last Irrigation
   - `SensorDeviceClass.TIMESTAMP`;
   - timezone-aware datetime or `None`.

## Tasks

1. Correct platform setup signature and call `async_add_entities`.
2. Entity classes must inherit both `CoordinatorEntity` and `SensorEntity`.
3. Use entity descriptions and a small generic entity implementation.
4. Set `_attr_has_entity_name = True`.
5. Use translation keys instead of hard-coded names.
6. Create one service-like DeviceInfo object per config entry to group entities.
7. Unique IDs must include `entry.entry_id` and the entity description key.
8. Use `native_value`, not `state`.
9. Availability must depend on coordinator refresh success for calculation entities.
10. Controller-only state entities should remain available when calculations temporarily fail if their state is still meaningful; document this choice.
11. Never perform I/O in entity properties.

## Tests

Create `tests/test_sensor.py` covering:

- all six entities are added;
- unique IDs differ between entries;
- device grouping;
- native values and units;
- classes and enum options;
- timestamp type;
- calculation entities become unavailable after coordinator failure;
- recovery makes them available;
- translated entity keys exist.

## Acceptance criteria

- Home Assistant entity registry receives six stable unique IDs per entry;
- no legacy state properties;
- multiple entries create no collisions;
- entities update when coordinator or controller state changes.

## Suggested commit

`feat: add solar irrigation diagnostic sensors`

---

# Phase 7 — Implement the irrigation controller core

## Objective

Provide safe start, timed stop, manual stop, and overlap prevention without real long sleeps.

## Required controller fields

```text
hass
entry
coordinator
pump_entity_id
status
last_execution
active_started_at
active_end_at
last_error
run_lock
stop_timer_unsub
daily_schedule_unsub
is_shutting_down
```

## `async_run` algorithm

1. Acquire an `asyncio.Lock` or reject if already running.
2. Reject if shutting down.
3. If automatic run and already executed today, return a no-op result.
4. Refresh coordinator immediately before choosing runtime.
5. If refresh fails, set error state and do not start pump.
6. Resolve duration:
   - override duration if supplied and validated;
   - otherwise coordinator runtime seconds.
7. If duration is zero:
   - do not call the pump;
   - persist today as executed;
   - set completed;
   - notify entities.
8. Validate pump entity:
   - exists;
   - switch domain;
   - not unavailable/unknown.
9. Call `switch.turn_on` with `blocking=True`.
10. Confirm the call did not raise. Optionally verify state after a short event-driven wait; do not rely on arbitrary sleeping in tests.
11. Persist execution immediately after successful start to prevent duplicate restart runs.
12. Set status running and store start/end times.
13. Schedule the stop using Home Assistant event helpers such as `async_track_point_in_time` or `async_call_later`.
14. Return promptly; do not hold an action call open for the full irrigation duration.

## Timed stop algorithm

1. Clear timer handle first to prevent duplicate callback use.
2. Call pump off with `blocking=True`.
3. In a `finally` block, clear active times.
4. Set status completed if off succeeded; error if it failed.
5. Persist controller state.
6. Notify entities.

## Manual stop algorithm

1. Cancel the pending stop callback.
2. If this controller has an active run, turn the configured pump off.
3. Clear active times.
4. Mark the day executed if the pump was successfully started earlier.
5. Set completed, or error if pump-off fails.
6. Persist and notify.
7. Calling stop while idle must be idempotent and safe.

## Safety rules

- no overlapping run;
- no second automatic run on the same date;
- no pump start on calculation failure;
- no pump start on unavailable pump;
- every successful on command has a planned off callback;
- unload and shutdown force off only when this integration owns an active run;
- service errors raise translated `ServiceValidationError` or `HomeAssistantError` rather than silently returning false;
- logs never contain vague “would go here” placeholders.

## Tests

Create `tests/test_irrigation.py` covering:

1. calculated-duration start;
2. override-duration start;
3. zero-duration no-op;
4. timer fires and turns pump off;
5. manual stop cancels timer;
6. stop while idle;
7. duplicate run rejected/no-op;
8. concurrent runs cannot overlap;
9. coordinator failure prevents on call;
10. missing pump prevents on call;
11. unavailable pump prevents on call;
12. turn-on service failure;
13. turn-off service failure;
14. unload during active run;
15. controller state notifications;
16. no test uses actual waiting—use Home Assistant time helpers and patched callbacks.

## Acceptance criteria

- actions return promptly;
- timer is recoverable and cancellable;
- pump is not left on in tested exception paths;
- duplicate and concurrent execution tests pass.

## Suggested commit

`feat: implement safe irrigation execution controller`

---

# Phase 8 — Implement daily scheduling, storage, and restart recovery

## Objective

Satisfy the exact once-per-day and restart requirements.

## Storage design

Use `homeassistant.helpers.storage.Store` with a key containing the config-entry ID.

Persist only JSON-safe values:

```json
{
  "last_execution": "ISO-8601 datetime or null",
  "active_started_at": "ISO-8601 datetime or null",
  "active_end_at": "ISO-8601 datetime or null",
  "status": "idle|scheduled|running|completed|error"
}
```

Validate loaded data. Corrupt data must log a warning, fall back safely, and never start the pump unexpectedly.

## Daily scheduler

1. Register a local-time callback for 06:00:00 using Home Assistant time helpers.
2. At callback:
   - check local date;
   - skip if already executed;
   - run automatically using fresh coordinator data.
3. After each day’s completion, status may become completed. Schedule remains registered for the next day.

## Startup recovery

After loading storage:

### Case A: prior active run has an end time in the future

- inspect configured pump state;
- if pump is on, restore running state and schedule remaining stop time;
- if pump is off, clear active state and mark completed or error with explanation;
- never restart the pump merely because storage says it was running.

### Case B: prior active run end time has passed

- force pump off if it is currently on and this entry owns the recorded run;
- clear active state;
- mark completed/error;
- do not re-run that day.

### Case C: Home Assistant starts after 06:00 and no execution occurred today

- run immediately after setup completes and source states are available;
- prevent race with the daily callback using the same run lock and date guard.

### Case D: Home Assistant starts before 06:00

- set scheduled state;
- wait for daily callback.

## Date semantics

Use Home Assistant local time, not naive `datetime.now()`. Compare local calendar dates. Store timezone-aware ISO timestamps.

## Tests

1. startup before 06:00 schedules only;
2. startup after 06:00 runs immediately;
3. startup after 06:00 but already executed does nothing;
4. exact 06:00 callback runs once;
5. restart during active run resumes stop timer without re-energizing pump;
6. restart after end time forces off and does not rerun;
7. corrupted storage is safe;
8. missing storage uses defaults;
9. DST transition day still runs once;
10. two entries schedule independently;
11. reload does not create duplicate callbacks;
12. manual stop followed by restart does not rerun that day.

## Acceptance criteria

- exactly once per local date under tested startup and callback races;
- active-run recovery never blindly turns a pump on;
- all timers/listeners are removable;
- persistence is entry-isolated.

## Suggested commit

`feat: add daily scheduling and restart recovery`

---

# Phase 9 — Implement Home Assistant actions properly

## Objective

Expose safe, multi-entry-aware actions with schemas and translated UI descriptions.

## Recommended action model

Because actions operate on one configured integration instance, target a config entry rather than asking the caller to pass an arbitrary pump entity.

### `solar_irrigation.run_now`

Fields:

- required `config_entry_id` selector limited to `solar_irrigation`;
- optional duration override in minutes with documented bounds.

Behavior:

- resolve a loaded config entry;
- call that entry’s controller;
- refresh calculation first when no override is supplied;
- raise meaningful translated exceptions on invalid entry, unloaded entry, invalid duration, unavailable data, or pump failure.

### `solar_irrigation.stop`

Fields:

- required `config_entry_id` selector limited to `solar_irrigation`.

Behavior:

- resolve loaded entry;
- call controller stop;
- idempotent while idle.

## Registration

1. Register actions in integration-level `async_setup`, once.
2. Do not register once per config entry.
3. Use Voluptuous/config-validation schemas or current service helper APIs.
4. Keep `services.yaml` as frontend documentation matching the Python schema exactly.
5. Use translations for action names, descriptions, and fields.

## Tests

Create `tests/test_services.py` covering:

1. run now with calculated duration;
2. run now with override;
3. stop;
4. invalid config entry;
5. unloaded config entry;
6. invalid override;
7. controller error propagated;
8. two entries route correctly;
9. actions registered only once;
10. schema and `services.yaml` field agreement.

## Acceptance criteria

- no arbitrary entity can be controlled through an action;
- correct entry is selected in multi-entry setups;
- action errors are user-readable;
- handlers accept `ServiceCall` correctly.

## Suggested commit

`feat: add run and stop integration actions`

---

# Phase 10 — Diagnostics, logging, localization, and documentation

## Objective

Make failures supportable and the integration understandable.

## Diagnostics

Add `diagnostics.py` returning:

- sanitized config-entry data and options;
- current normalized source values;
- calculation result;
- coordinator success/last update information;
- controller status;
- last execution;
- active start/end;
- source and pump entity states;
- last controller error.

Do not include secrets or unnecessary personal data. Entity IDs are generally needed for support, but document what is exposed.

## Logging

Use parameterized logging rather than f-strings.

Log at appropriate levels:

- debug: configuration identifiers, calculations, schedule creation;
- info: irrigation start, stop, completion, restart recovery action;
- warning: invalid/corrupt stored state, unexpected pump state;
- errors should generally be surfaced through coordinator/action exceptions without repetitive spam.

Never log every hourly unavailable refresh at error level if the coordinator already manages availability transitions.

## Localization

Complete:

- config and options flow;
- errors and abort reasons;
- all six entity names;
- enum state values;
- action names/descriptions/fields;
- exceptions where supported;
- issue messages if repairs are later added.

Keep `strings.json` and `translations/en.json` synchronized.

## README

Replace current README completely. Include:

1. what the integration does;
2. safety warning that it controls a physical irrigation switch;
3. prerequisites;
4. HACS custom repository installation;
5. restart requirement after installation/update;
6. config-flow instructions;
7. explanation of actual + remaining solar calculation;
8. exact formula and example;
9. fixed 06:00 scheduling behavior;
10. restart recovery behavior;
11. action examples;
12. entity list;
13. supported units;
14. zero-runtime behavior;
15. troubleshooting unavailable sensors/pump;
16. diagnostics download instructions;
17. removal instructions;
18. development/testing instructions;
19. limitations and future extensions.

Do not claim screenshots exist unless added.

## Tests

- diagnostics shape and values;
- sensitive-data redaction if any sensitive values are introduced;
- translation files parse and contain required keys;
- README examples match actual action schema.

## Acceptance criteria

- diagnostics can be downloaded for an entry;
- logs explain failures without flooding;
- UI contains no raw translation keys;
- README describes only tested behavior.

## Suggested commit

`docs: add diagnostics localization and user guide`

---

# Phase 11 — Full test matrix and release gates

## Objective

Prove the integration works before any release/version bump.

## Required automated checks

```bash
ruff format --check .
ruff check .
python -m compileall custom_components/solar_irrigation
pytest -q
pytest --cov=custom_components.solar_irrigation --cov-report=term-missing
```

Target meaningful coverage above 95%, with safety-critical controller paths at 100% branch coverage where practical.

Add and pass:

- HACS Action;
- hassfest action;
- test workflow on the minimum supported Home Assistant/Python combination;
- test workflow on the latest stable Home Assistant combination;
- optionally beta/nightly compatibility as non-blocking initially.

## Required manual Home Assistant test

Use a non-production Home Assistant instance and safe test entities, not a real pump initially.

Create:

- two `input_number` or template sensors representing solar values with correct energy units;
- one `input_boolean` exposed through a template switch, or another harmless test switch;
- a second independent test switch for multi-entry testing.

Verify:

1. HACS custom repository installation;
2. restart;
3. config flow appears;
4. entry setup succeeds with no log traceback;
5. six entities appear;
6. calculated values match expected formula;
7. source unavailable makes calculation entities unavailable;
8. source recovery restores them;
9. run-now starts test switch and schedules stop;
10. stop turns it off;
11. unload/reload leaves no duplicate callbacks;
12. restart during a short active run recovers correctly;
13. startup after 06:00 behavior using patched/test time or temporary development-only schedule;
14. two entries are independent;
15. diagnostics download works;
16. deletion/removal works.

Do not test long real durations; use short overrides on harmless entities.

## Release-blocking failures

Any of these blocks release:

- exception during startup, setup, reload, or unload;
- entity unavailable for unexplained reasons;
- action TypeError;
- duplicate automatic watering;
- pump can remain on after stop, reload, or tested failure;
- cross-entry control;
- missing translation;
- HACS/hassfest failure;
- committed cache file;
- README/version mismatch;
- tests skipped without a written reason.

## Acceptance criteria

All automated and manual gates pass and evidence is recorded in a release checklist.

## Suggested commit

`test: complete integration behavior and release validation`

---

# Phase 12 — Release

## Objective

Create the first honest functional release.

## Tasks

1. Choose semantic version based on repository history and compatibility. For a first proven functional release, `0.1.0` is clean; if preserving existing public version history, choose the next appropriate version and document why.
2. Change only `manifest.json` version.
3. Ensure `hacs.json` has no version.
4. Update changelog/release notes with:
   - functional scope;
   - supported Home Assistant minimum;
   - limitations;
   - upgrade notes;
   - safety notes.
5. Commit the version change.
6. Create a Git tag matching the manifest version exactly.
7. Create a full GitHub release, not only a tag.
8. Confirm HACS and hassfest workflows pass against the release.
9. Install the released artifact in the test Home Assistant instance and repeat smoke tests.

## Acceptance criteria

- manifest, tag, and release version match;
- release artifact contains the expected component files;
- released artifact installs from HACS;
- no development-only files are packaged unexpectedly;
- smoke test passes from the release, not only the working tree.

## Suggested commit

`release: solar irrigation <version>`

---

## 9. Required Test Inventory

Hermes must not consider the project complete until this inventory exists and passes.

### Config flow

- form;
- success;
- defaults;
- duplicate pump;
- invalid divisor;
- invalid values;
- source validation;
- options;
- reload.

### Calculation

- normal;
- zero;
- clamp;
- rounding;
- unit conversion;
- unknown/unavailable;
- non-numeric;
- negative;
- non-finite;
- incompatible unit.

### Setup/lifecycle

- setup;
- retry on source failure;
- entity creation;
- unload;
- reload;
- multi-entry isolation;
- listener cleanup.

### Controller

- start;
- timed stop;
- manual stop;
- zero no-op;
- concurrency;
- duplicate date guard;
- service failures;
- unavailable pump;
- unload during run;
- notification updates.

### Scheduling/recovery

- before 06:00;
- after 06:00;
- exactly at callback;
- already executed;
- restart during run;
- restart after expected end;
- corrupt storage;
- DST;
- multi-entry;
- no duplicate callbacks.

### Actions

- route by config entry;
- calculated duration;
- override;
- stop;
- invalid/unloaded entry;
- validation errors;
- multiple entries.

### Entities/diagnostics

- entity metadata;
- units/device classes;
- unique IDs;
- availability;
- enum states;
- timestamp;
- diagnostics payload;
- translations.

---

## 10. Definition of Done

The component is functional only when every statement below is true.

1. It installs from HACS as a custom repository.
2. Home Assistant restarts with no `solar_irrigation` traceback.
3. Config flow completes with valid inputs.
4. Duplicate pump configuration is blocked.
5. Six diagnostic sensors are created.
6. Calculation matches the documented formula.
7. Wh/kWh/MWh handling is correct.
8. Invalid source data makes calculation entities unavailable and prevents pump start.
9. Daily 06:00 execution occurs once per local date.
10. Startup after 06:00 catches up only if not already executed.
11. Run-now and stop actions work and select the correct config entry.
12. A zero duration never pulses the pump.
13. Overlapping runs are impossible.
14. Timed stop, manual stop, unload, and restart paths do not leave the pump on in tested scenarios.
15. Last execution and active timer state survive restart.
16. Two config entries operate independently.
17. Reload/unload leaves no listeners or timers behind.
18. Diagnostics are available.
19. README matches actual behavior.
20. Ruff, pytest, coverage, HACS Action, and hassfest all pass.
21. No placeholder code remains.
22. Release version, tag, and manifest match.

---

## 11. First Hermes Work Order

Give Hermes only the following first assignment. Do not ask it to implement the whole plan in one run.

> Read `IrrigationManager.md`, `FixError.md`, and every file under `custom_components/solar_irrigation`. Execute Phase 0 and Phase 1 only from `Hermes_Solar_Irrigation_Development_Plan.md`. Do not change the integration version. Do not implement scheduling or irrigation runtime behavior yet. Add a valid test/development scaffold, remove cache artifacts, correct HACS and manifest metadata, add `strings.json`, repair `services.yaml` structure, remove unsupported readiness claims, and decide/remove the unused custom switch platform as specified. Run Ruff, compilation, pytest collection, HACS validation, and hassfest where available. Report exact commands and results, changed files, unresolved failures, and `git diff --stat`. Do not claim the integration is functional or release-ready.

After Phase 0-1 are reviewed and accepted, give Hermes Phase 2 only, then continue sequentially.

---

## 12. Authoritative References Hermes Should Check During Development

Use current official documentation rather than model memory, especially when APIs differ from this plan.

- Home Assistant integration manifest: https://developers.home-assistant.io/docs/creating_integration_manifest/
- Home Assistant config flow: https://developers.home-assistant.io/docs/core/integration/config_flow/
- Home Assistant config entries: https://developers.home-assistant.io/docs/config_entries_index/
- Runtime data in config entries: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/runtime-data/
- Config entry unloading: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/config-entry-unloading/
- Sensor entity API: https://developers.home-assistant.io/docs/core/entity/sensor/
- Integration actions: https://developers.home-assistant.io/docs/dev_101_services/
- Integration diagnostics: https://developers.home-assistant.io/docs/core/integration/diagnostics/
- Entity naming and translations: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/has-entity-name/
- Test structure: https://developers.home-assistant.io/docs/creating_integration_tests_file_structure/
- HACS general publishing requirements: https://hacs.xyz/docs/publish/start/
- HACS integration requirements: https://hacs.xyz/docs/publish/integration/
- HACS validation action: https://hacs.xyz/docs/publish/action/

When current official documentation conflicts with this plan, follow the official documentation and record the change with a citation in the phase report.