# Validation result for Solar Irrigation 2.5

The uploaded baseline reported 26 passing tests and 72 percent branch coverage.
The version 2.5 source expands the suite to 78 behavioral and repository test
functions, including pulse-and-soak execution, daily-budget enforcement,
actuator races and failures, restart accounting, delayed solar samples,
configuration validation, diagnostics, number and sensor entities, actions, and
watering-window behavior.

Validation completed in the packaging environment:

- all integration and test Python files compile successfully;
- every production class, function, coroutine, and method has a docstring;
- no simple unused imports were detected by an AST check;
- `strings.json` and `translations/en.json` are structurally identical;
- the manifest reports version 2.5;
- five local repository-validation tests pass;
- a dependency-free smoke simulation verifies a seven-minute event is delivered
  as 3 minutes water, 15 minutes soak, 3 minutes water, 15 minutes soak, and
  1 minute water, with 420 delivered seconds and three pulses;
- a second smoke event verifies shared daily-budget accounting.

The complete Home Assistant pytest suite, Ruff, branch-coverage gate, and Docker
Hassfest could not be run in this packaging environment because the Home
Assistant test dependencies and Docker image were unavailable and network
package installation was blocked. Run the authoritative local quality gate:

```bash
make quality
```

If only behavioral coverage is needed while iterating:

```bash
make test-coverage
```
