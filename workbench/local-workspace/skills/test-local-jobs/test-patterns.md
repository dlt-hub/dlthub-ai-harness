# Test patterns

The examples test this job, listed in `__deployment__.py`:

```python
# numbers_pipeline.py
import dlt
from dlt.hub import run


@dlt.resource
def numbers(limit: int):
    yield [{"id": i} for i in range(limit)]


@run.pipeline("numbers_pipeline")
def load_numbers(limit: int = dlt.config.value) -> None:
    pipeline = dlt.pipeline(
        pipeline_name="numbers_pipeline", destination="warehouse", dataset_name="numbers_data"
    )
    pipeline.run(numbers(limit))
```

with `.dlt/tests.config.toml`:

```toml
[destination.warehouse]
destination_type = "duckdb"

[jobs.numbers_pipeline]
limit = 3
```

## `tests/conftest.py`

```python
import os
import shutil

import dlt
import pytest


def pytest_sessionstart(session: pytest.Session) -> None:
    # before pytest imports the test modules and the jobs that they import
    dlt.current.workspace().switch_profile("tests")


@pytest.fixture(autouse=True)
def clean_tests_profile() -> None:
    # each test starts without the pipeline state and the local data of `tests`
    workspace = dlt.current.workspace()
    for folder in (workspace.data_dir, workspace.local_dir):
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder)
```

The fixture creates the folders again: DuckDB does not create a missing folder. Add `pythonpath = .` to the
pytest settings, so that the tests import the jobs and `__deployment__.py` from the project root.

## The job and the job run

```python
import shutil
import subprocess

import dlt
import pytest

import __deployment__
from numbers_pipeline import load_numbers


def local_run(*args: str) -> subprocess.CompletedProcess:
    dlthub = shutil.which("dlthub")
    return subprocess.run(
        [dlthub, "--non-interactive", "--profile", "tests", "local", "run", *args],
        capture_output=True,
        text=True,
    )


def row_count(table: str) -> int:
    # the same pipeline as in the job: name, destination and dataset name
    pipeline = dlt.pipeline("numbers_pipeline", destination="warehouse", dataset_name="numbers_data")
    return len(pipeline.dataset()[table].fetchall())


def test_load_numbers() -> None:
    load_numbers(limit=2)
    assert row_count("numbers") == 2


def test_load_numbers_takes_tests_settings() -> None:
    load_numbers()  # limit = 3 from [jobs.numbers_pipeline] in tests.config.toml
    assert row_count("numbers") == 3


def test_load_numbers_end_to_end() -> None:
    result = local_run("load_numbers", "-c", "limit=4")
    assert result.returncode == 0, result.stderr
    assert row_count("numbers") == 4


@pytest.mark.parametrize("job", __deployment__.__all__)
def test_job_resolves(job: str) -> None:
    result = local_run(job, "--dry-run")
    assert result.returncode == 0, result.stderr
```

`dlthub local run` returns the exit code of the job. For a job that must fail, assert `returncode == 1`.

## A pipeline at the module level

The cleanup fixture removes the working folder of a pipeline that a module created at import. Reset the pipeline
after the cleanup, and read its dataset from it:

```python
import pytest

from orders_pipeline import load_orders, pipeline


@pytest.fixture(autouse=True)
def fresh_pipeline(clean_tests_profile: None) -> None:
    pipeline.drop()


def test_load_orders() -> None:
    load_orders()
    assert len(pipeline.dataset()["orders"].fetchall()) == 5
```

## An agent job

Install `pytest-asyncio`. Await the job, then read its job result. dlt sends nothing to the platform.

```python
import pytest

from my_agents import crash_inspector


@pytest.mark.asyncio
async def test_crash_inspector() -> None:
    run_context = {"run_id": "r-test", "trigger": "job.fail:jobs.ingest", "refresh": False}
    report = await crash_inspector(failed_run_id="r-failed-42", run_context=run_context)
    assert report["status"] == "succeeded"
    job_result = crash_inspector.last_job_result
    assert job_result["trace"]["total_tokens"] < 200_000
```

Call a sync decorated function without `await`. More: https://dlthub.com/docs/hub/agents.md#test-agent-jobs
