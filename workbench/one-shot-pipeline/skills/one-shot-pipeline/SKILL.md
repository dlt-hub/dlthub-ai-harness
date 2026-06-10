---
name: quick-pipeline
description: Create and run a custom REST API pipeline on dltHub. Use when the user names an API or data source they want to connect to and load data from.
argument-hint: "<api-name> [endpoint-hint]"
---

Build a minimal single-endpoint pipeline for the user's API and run it on dltHub with a row limit. No local execution. Goal is a working first run, not a production pipeline.

**This skill is for REST API / HTTP API sources only.** If the user is asking about:
- A SQL database (Postgres, MySQL, BigQuery, etc.) → install the `sql-database-pipeline` toolkit
- Files or object storage (S3, GCS, CSV, Parquet, SFTP, etc.) → install the `filesystem-pipeline` toolkit

To install: `uv run dlthub --non-interactive ai toolkit install <toolkit-name>`

**This skill loads 3 rows only.** It is a first-run validation, not a production pipeline.

Only mention toolkit installation if the user explicitly asks for something this skill does not cover (full data load, pagination, incremental loading, schema hints, multiple endpoints). Do not proactively suggest installing toolkits — mention them only when directly asked.

**Reference**: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic

## Step 1 — Research the API

Check for a verified source first:

```
uv run dlthub --non-interactive pipeline init --list-sources | grep -i <api-name>
```

If a match is found, tell the user: "A verified source exists for `<api-name>` — you can use `dlthub pipeline init <source> warehouse` for a maintained connector. Continuing with custom pipeline unless you say otherwise." Then proceed.

Web search: `<api-name> REST API documentation` and `<api-name> REST API authentication`.

Extract:
- `base_url` — root URL shared by all endpoints (e.g. `https://api.github.com`)
- Auth method — Bearer token, API key (header or query param), HTTP Basic, or none
- One clear endpoint — the most useful starting resource (e.g. `/repos`, `/orders`, `/events`)
- Response wrapper key — does data sit under `"data"`, `"items"`, `"results"`, or is it a root array?

One or two targeted searches is enough. If auth docs are on a separate page, fetch it too.

## Step 2 — Write the pipeline file

Create `<source>_pipeline.py`. Follow the exact pattern from `pipeline.py`:

```python
"""<Source> dlt pipeline.

Loads <endpoint> from the <Source> REST API into the dltHub warehouse.
"""

import dlt
from dlt.sources.rest_api import rest_api_source
from dlt.hub import run


def <source>():
    return rest_api_source(
        {
            "client": {
                "base_url": "<base_url>",
                # Add auth here if the API requires it — see auth patterns below
            },
            "resources": [
                {
                    "name": "<endpoint>",
                    "endpoint": {
                        "path": "<path>",
                        "data_selector": "<wrapper_key>",  # e.g. "data", "items" — omit if response is a root array
                    },
                    "primary_key": "id",  # adjust to the resource's actual unique key
                },
            ],
        }
    )


@run.pipeline("<source>_pipeline")
def load_<source>():
    """Load <endpoint> from <Source>."""

    pipeline = dlt.pipeline(
        pipeline_name="<source>_pipeline",
        destination="warehouse",
        dataset_name="<source>",
    )

    load_info = pipeline.run(<source>().add_limit(3), write_disposition="replace")
    print(load_info)


if __name__ == "__main__":
    load_<source>()
```

### Auth patterns

Pick the one that matches the API. Add it under `"client"`:

```python
# Bearer token
"auth": {"type": "bearer", "token": dlt.secrets["sources.<source>.token"]}

# API key in header
"auth": {"type": "api_key", "name": "X-API-Key", "api_key": dlt.secrets["sources.<source>.api_key"], "location": "header"}

# API key in query param
"auth": {"type": "api_key", "name": "api_key", "api_key": dlt.secrets["sources.<source>.api_key"], "location": "query"}

# HTTP Basic
"auth": {"type": "http_basic", "username": dlt.secrets["sources.<source>.username"], "password": dlt.secrets["sources.<source>.password"]}
```

### Rules

- `destination="warehouse"` always — already configured in `.dlt/config.toml`
- `.add_limit(3)` always — this is a validation run, not a full load
- Omit `data_selector` if the response is a root JSON array
- Omit pagination config — `.add_limit(3)` caps the run; let dlt auto-detect or stop naturally
- Omit auth entirely if the API is public

## Step 3 — Update `__deployment__.py`

Add one import and one entry to `__all__`:

```python
from <source>_pipeline import load_<source>

__all__ = ["load_<source>", ...]  # add as a string alongside existing entries
```

## Step 4 — Handle credentials

**Skip this step entirely if the API is public (no auth needed).**

Do not read or write `.dlt/secrets.toml` directly — use the CLI instead.

**4a. Check what's already configured:**

```
uv run dlthub ai secrets list
uv run dlthub ai secrets view-redacted
```

`view-redacted` shows all configured keys with values replaced by `***`. If `[sources.<source>]` already has the required field populated (shown as `***`), skip to Step 5.

**4b. If the credential is missing**, show the user exactly what to add:

> Open `.dlt/secrets.toml` (not `dev.secrets.toml`) and add:
>
> ```toml
> [sources.<source>]
> token = "paste-your-token-here"
> ```
>
> Get your token from: `<direct link from API docs>`

Use `secrets.toml` (workspace-scoped) so credentials are visible to all profiles — credentials in `dev.secrets.toml` are not visible to the platform's prod profile and the job will fail.

**Stop and wait** for the user to confirm they've added the credential.

**4c. Verify** the credential is in place:

```
uv run dlthub ai secrets view-redacted
```

Confirm `[sources.<source>].<field>` now shows `***`. If it's still absent, the user hasn't saved or used the wrong section name — ask them to check before continuing.

## Step 5 — Deploy and run

```
uv run dlthub --non-interactive deploy
uv run dlthub --non-interactive run load_<source> -f
```

Report what table was created and how many rows loaded (visible in log output).

> **Note:** The data loaded in this run is not queryable after the job finishes. The platform's default warehouse destination uses an ephemeral DuckDB instance that exists only for the duration of the pipeline run — once the job ends, the data is gone. If you want to inspect or query your data, you'll need a persistent destination (e.g. MotherDuck, BigQuery, Snowflake). Would you like to set one up?

---

## If the job fails

Fix the pipeline file and re-run from Step 5.

| Symptom | Likely cause | Fix |
|---|---|---|
| 0 rows loaded | Wrong `data_selector` | Check raw response shape in logs; update key or omit entirely |
| 401 / 403 error | Auth misconfigured | Verify credential is in `secrets.toml` (not `dev.secrets.toml`) and header name/location are correct |
| Job runs indefinitely | Paginator looping | Add `"paginator": "single_page"` to the resource's `endpoint` config |
| `ConfigFieldMissingException` | Secret key path mismatch | Check that `dlt.secrets["sources.<source>.<field>"]` matches the `[sources.<source>]` section in `secrets.toml` |
| `deploy` fails immediately | Not logged in | Run `dlthub login` then `dlthub workspace connect` |
| `deploy` fails immediately | Missing `pyproject.toml` | Run `uv init` in the project root |
| `from dlt.hub import run` error | `dlt[hub]` not installed | Run `uv add "dlt[hub]"` |
| Job does nothing / 0 runs | Missing `if __name__ == "__main__":` | Add the block to the pipeline script |