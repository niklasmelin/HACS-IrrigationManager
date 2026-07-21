# Home Assistant Test Skill

Use the repository Makefile for all test tasks.

## Commands

```bash
make
make help
make setup_test_env
make test
make test-unit
make test-repository
make test-hassfest
make clean_test_env
```

## Workflow

1. Run `make setup_test_env` once.
2. Run `make test-unit` during development.
3. Run `make test-repository` after metadata or packaging changes.
4. Run `make test-hassfest` after manifest, services, translations, or platform changes.
5. Run `make test` before declaring work complete.

Do not use a production Home Assistant instance. Tests must use fixtures from `tests/conftest.py`.

When configuration keys change, update the production constants first, then update the shared `config_entry_data` fixture.

Never claim success unless the relevant command exits with code `0`. Report the exact command, failures, skipped tests, and final result.
