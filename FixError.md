# FixErrors.md

# Solar Irrigation HACS Integration -- Issues Found

This document summarizes the issues found during the review and
recommends fixes.

## 1. Platform forwarding missing (**Critical**)

### Problem

`__init__.py` does not forward the config entry to any Home Assistant
platforms.

Current code attempts to execute:

``` python
await hass.async_add_executor_job(
    entry.data.get("setup_platforms", lambda: None)
)
```

`setup_platforms` does not exist in `entry.data`, therefore no entities
are ever loaded.

### Fix

Define:

``` python
PLATFORMS = ["sensor"]
```

(or additional platforms when implemented)

Then use:

``` python
await hass.config_entries.async_forward_entry_setups(
    entry,
    PLATFORMS,
)
```

During unload:

``` python
await hass.config_entries.async_unload_platforms(
    entry,
    PLATFORMS,
)
```

------------------------------------------------------------------------

## 2. Coordinator never instantiated (**Critical**)

### Problem

`SolarIrrigationCoordinator` exists but is never created.

### Fix

Inside `async_setup_entry()`:

``` python
coordinator = SolarIrrigationCoordinator(...)
await coordinator.async_config_entry_first_refresh()

hass.data.setdefault(DOMAIN, {})
hass.data[DOMAIN][entry.entry_id] = coordinator
```

Entities should retrieve the coordinator from `hass.data`.

------------------------------------------------------------------------

## 3. Entity selector configuration

### Problem

Selectors use:

``` python
selector.EntitySelector()
```

which accepts any entity.

### Fix

Use:

``` python
selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor")
)
```

and

``` python
selector.EntitySelector(
    selector.EntitySelectorConfig(domain="switch")
)
```

------------------------------------------------------------------------

## 4. Constant naming typo

### Problem

The constant `CONF_IRrigation_ENTITY` has inconsistent capitalization.

### Fix

Rename everywhere to:

``` python
CONF_IRRIGATION_ENTITY
```

Update all imports and references.

------------------------------------------------------------------------

## 5. Add async_setup()

Recommended:

``` python
async def async_setup(hass, config):
    return True
```

------------------------------------------------------------------------

## 6. Services are documented but not registered

### Problem

`services.yaml` documents services only.

### Fix

Register services in `async_setup()` using:

``` python
hass.services.async_register(...)
```

------------------------------------------------------------------------

## 7. Update interval units

### Problem

Coordinator currently uses:

``` python
timedelta(seconds=update_interval)
```

Configuration implies minutes or hours.

### Fix

Use:

``` python
timedelta(minutes=update_interval)
```

or make the unit explicit in the configuration flow.

------------------------------------------------------------------------

## 8. Verify manifest.json

Ensure it contains:

``` json
{
  "config_flow": true
}
```

without this the Config Flow will never start.

------------------------------------------------------------------------

# Recommended implementation order

1.  Fix `__init__.py`
2.  Instantiate the coordinator
3.  Forward platforms
4.  Correct constant names
5.  Register services
6.  Verify `manifest.json`
7.  Test Config Flow
8.  Test entity creation
9.  Test irrigation execution
10. Add unit tests

Following this order will align the integration with the standard Home
Assistant architecture.