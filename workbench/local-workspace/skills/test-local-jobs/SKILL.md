---
name: test-local-jobs
description: Write pytest tests that run dlt jobs on the `tests` profile. Call a job in the test, run it end to end with `dlthub local run`, check that every job in `__deployment__.py` resolves, and test agent jobs. Use when the user wants tests or a CI check for pipelines and jobs.
---

# Test jobs

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/profiles.md (run tests on the `tests` profile) |
https://dlthub.com/docs/hub/pipeline-operations/deployments.md

Tests run on the `tests` profile. It is local and has its own state and data folders, so tests never touch the
pipelines on `dev`. Tests never run with a remote profile.

## 1. Prepare the `tests` profile

1. In `.dlt/tests.config.toml`, point the destinations of the jobs at DuckDB, for example
   `destination_type = "duckdb"` under `[destination.warehouse]`.
2. Keep the job runs small: set job arguments in `[jobs.<module>]` of `tests.config.toml`, for example `limit = 10`.
3. Add a `conftest.py` to the tests folder of the workspace (for example `tests/conftest.py`): one fixture makes `tests` the active profile, one empties its folders before each test.
   See [test-patterns.md](test-patterns.md).
4. Create the pipelines inside the jobs. pytest imports the test modules before the fixture runs, so a pipeline
   created at the module level keeps the `dev` profile. If you cannot move the pipeline into the job, run the tests
   with `WORKSPACE__PROFILE=tests uv run pytest`.

## 2. Pick the tests

| Test | How | Checks |
|---|---|---|
| the job | call the job function, with arguments or with the settings of `tests` | the loaded data |
| the job run | `dlthub --non-interactive --profile tests local run <job> -c key=value` in a subprocess | the exit code and the loaded data |
| `__deployment__.py` | `dlthub local run <job> --dry-run` for each name in `__all__` | every job resolves |
| an agent job | `await` the job, then read `<job>.last_job_result` | the agent output and the job result |

Write one test per job at least, and one dry run per job in `__deployment__.py`. [test-patterns.md](test-patterns.md)
has an example of each.

- A call in the test gives the job its settings from `[jobs.<module>]`, but not `run_context`. If the job reads
  `run_context`, pass it yourself.
- If a source calls an API, give a small `limit`, or mock the HTTP calls.
- Check the data with `dlt.pipeline("<pipeline name>").dataset()`, for example the row count of a table.

## 3. Run and debug the tests

1. Run all tests from the project root: `uv run pytest tests`. If `pytest` is missing, add it to the dev
   dependencies. DuckDB needs no credentials, so the tests also run in CI.
2. If a test fails, inspect the pipeline that it ran: `dlthub --profile tests local pipeline trace <pipeline>`,
   `dlthub --profile tests local pipeline failed-jobs <pipeline>`.
3. To remove the state and the data of `tests`, run `dlthub --profile tests local clean`.
