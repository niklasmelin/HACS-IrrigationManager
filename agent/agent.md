# Repository Layout

This repository contains a Home Assistant custom integration named `solar_irrigation`.

```text
.
├── agent
│   ├── Developmentplan.md
│   ├── FixError.md
│   ├── hacs-test-skill
│   │   └── SKILL.md
│   └── IrrigationManager.md
├── custom_components
│   └── solar_irrigation
│       ├── config_flow.py
│       ├── const.py
│       ├── coordinator.py
│       ├── __init__.py
│       ├── irrigation.py
│       ├── manifest.json
│       ├── sensor.py
│       ├── services.yaml
│       ├── strings.json
│       └── translations
│           └── en.json
├── hacs.json
├── Makefile
├── pytest.ini
├── README.md
├── tests
│   ├── conftest.py
│   ├── requirements_test.txt
│   ├── test_init.py
│   └── test_repository_validation.py
└── validate_integration.py
```

## Agent Documentation

* `agent/IrrigationManager.md`
  Main functional and architectural context for the integration.

* `agent/FixError.md`
  Known defects, previous fixes, and unresolved issues.

* `agent/Developmentplan.md`
  Current implementation plan and task sequence.

* `agent/hacs-test-skill/SKILL.md`
  Instructions for setting up and running the local test suite.

Read these files before modifying the integration.

## Integration Source

All production integration code is located under:

```text
custom_components/solar_irrigation/
```

* `__init__.py`
  Config-entry setup, unloading, service registration, and runtime initialization.

* `config_flow.py`
  Home Assistant UI configuration and options flow.

* `const.py`
  Domain name, configuration keys, defaults, platforms, and shared constants.

* `coordinator.py`
  Data refresh, sensor reading, irrigation calculations, and coordinator state.

* `irrigation.py`
  Irrigation execution, scheduling, persistence, and switch-control logic.

* `sensor.py`
  Sensor entity definitions and platform setup.

* `manifest.json`
  Home Assistant integration metadata and dependencies.

* `services.yaml`
  Service definitions exposed by the integration.

* `strings.json`
  Default frontend text, configuration flow strings, services, and entity names.

* `translations/en.json`
  English translations corresponding to `strings.json`.

## Repository Metadata

* `hacs.json`
  HACS repository metadata.

* `README.md`
  User-facing installation, configuration, and usage documentation.

## Testing

All tests are located under:

```text
tests/
```

* `conftest.py`
  Shared fixtures, including config-entry test data and Home Assistant test setup.

* `test_init.py`
  Config-entry setup, platform forwarding, runtime initialization, and unloading tests.

* `test_repository_validation.py`
  Local repository checks and Hassfest validation.

* `requirements_test.txt`
  Python dependencies for the isolated test environment.

* `pytest.ini`
  Pytest configuration and custom markers.

* `Makefile`
  Primary interface for setting up and running tests.

Use:

```bash
make help
make setup_test_env
make test
```

Do not use a production Home Assistant instance for testing.

## Legacy Validation

* `validate_integration.py`
  Legacy or supplemental validation script. Do not treat this script as sufficient proof that the integration works.

The authoritative validation commands are the Makefile test targets and pytest suite.

## Agent Rules

1. Read the files under `agent/` before starting work.
2. Modify production code only under `custom_components/solar_irrigation/`.
3. Keep shared configuration keys in `const.py`.
4. Keep test config-entry mappings in `tests/conftest.py`.
5. Add or update tests for every behavioral change.
6. Run `make test-unit` during development.
7. Run `make test-repository` after metadata or packaging changes.
8. Run `make test-hassfest` after changes to manifests, services, translations, or platforms.
9. Run `make test` before declaring the task complete.
10. Report the exact test commands, exit results, failures, and skipped tests.
