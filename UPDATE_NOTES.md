# Solar Irrigation 2.3 controller-state synchronization fix

Updated files:

- `custom_components/solar_irrigation/irrigation.py`
- `custom_components/solar_irrigation/__init__.py`
- `tests/test_irrigation.py`

The controller now subscribes to the configured switch or valve state. If the
entity turns off outside the controller timer, the active timer is cancelled,
delivered runtime is accounted for, and the controller returns to `monitoring`.
If the entity becomes `unknown` or `unavailable` during irrigation, the run is
ended and controller status becomes `error`.

Copy the package contents over the repository root, then run:

```bash
make test
```
