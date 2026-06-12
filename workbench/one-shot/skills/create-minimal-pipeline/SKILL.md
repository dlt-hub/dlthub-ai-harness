---
name: create-minimal-pipeline
description: Build and run a minimal REST API pipeline locally against DuckDB. Use when the user wants to create a REST API pipeline, names a REST API source and/or endpoint they want to connect to and load data from, or says "Build a dlt pipeline for [source] API and load data from [endpoint] into DuckDB".
argument-hint: "[api-name] [endpoint-hint]"
---

Build a minimal single-endpoint pipeline and run it locally against DuckDB. The finish line is `dlthub local show` — the moment the user sees their loaded data in the local UI. Every feature beyond the minimum (pagination, incremental loading, multiple endpoints) increases run time and failure surface, delaying that moment.

**This skill is for REST API / HTTP API sources only.** If the user is asking about:
- A SQL database (Postgres, MySQL, BigQuery, etc.) → install the `sql-database-pipeline` toolkit
- Files or object storage (S3, GCS, CSV, Parquet, SFTP, etc.) → install the `filesystem-pipeline` toolkit

To install: `uv run dlthub --non-interactive ai toolkit install <toolkit-name>`

**This skill loads 50 rows only.** It is a first-run validation, not a production pipeline.

Only propose toolkit installation if the user explicitly asks for something this skill does not cover (full data load, pagination, incremental loading, schema hints, multiple endpoints). Do not proactively suggest installing toolkits — mention them only when directly asked.

**Reference**: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic

## Step 0 — No source named?

If the user hasn't named a specific API, run:

```
uv run dlthub --non-interactive pipeline init --list-sources
```

Take the first 3 sources from the output and suggest them:

> Here are a few real sources you can try:
> - github
> - hubspot
> - stripe_analytics
>
> There are more available — run `uv run dlthub --non-interactive pipeline init --list-sources` to see the full list.

Wait for the user to pick one, then continue to Step 1.

## Step 1 — Research the API

Check for a verified source first. If you already fetched the sources list in Step 0, grep that output directly. Otherwise run:

```
uv run dlthub --non-interactive pipeline init --list-sources | grep -i <api-name>
```

If a match is found, tell the user: "A verified source exists for `<api-name>` — you can use `dlthub pipeline init <source> duckdb` for a maintained connector." Then proceed with the custom pipeline.

Use your web search tool directly — do not spawn subagents, research agents, or delegate this step. One or two inline searches is all that's needed.

Web search: `<api-name> REST API documentation` and `<api-name> REST API authentication`.

Extract:
- `base_url` — root URL shared by all endpoints (e.g. `https://api.github.com`)
- Auth method — Bearer token, API key (header or query param), HTTP Basic, or none
- One clear endpoint — if the user named one in their prompt, use it; otherwise pick the most useful starting resource (e.g. `/repos`, `/orders`, `/events`)
- Response wrapper key — does data sit under `"data"`, `"items"`, `"results"`, or is it a root array?

One or two targeted searches is enough. If auth docs are on a separate page, fetch it too.

## Step 2 — Write the pipeline file

Create `<source>_pipeline.py`. Follow the exact pattern from `pipeline.py`:

### Rules

- `destination="duckdb"` always — runs locally against DuckDB
- `.add_limit(50, count_rows=True)` always — row limit, not page limit; omitting `count_rows=True` silently loads the entire dataset when a paginator is active
- Omit `data_selector` if the response is a root JSON array; if the wrapper key is ambiguous or undocumented, omit it first and check the row count — dlt will raise a clear error if the selector is wrong
- Omit pagination config — `.add_limit(50, count_rows=True)` caps the run; let dlt auto-detect or stop naturally

```python
"""<Source> dlt pipeline.

Loads <endpoint> from the <Source> REST API into the duckdb.
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
        destination="duckdb",
        dataset_name="<source>",
    )

    load_info = pipeline.run(<source>().add_limit(50, count_rows=True), write_disposition="replace")  # row limit, not page limit
    print(load_info)


if __name__ == "__main__":
    load_<source>()
```

If the API is public (no auth needed), skip auth entirely — omit the `"auth"` key from `"client"`.

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

## Step 3 — Handle credentials

**Skip this step entirely if the API is public (no auth needed).**

Do not read or write `.dlt/secrets.toml` directly — use the CLI instead.

**3a. Check what's already configured:**

```
uv run dlthub ai secrets list
uv run dlthub ai secrets view-redacted
```

`view-redacted` shows all configured keys with values replaced by `***`. If `[sources.<source>]` already has the required field populated (shown as `***`), skip to Step 4.

**3b. If the credential is missing**, show the user exactly what to add:

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

**3c. Verify** the credential is in place:

```
uv run dlthub ai secrets view-redacted
```

Confirm `[sources.<source>].<field>` now shows `***`. If it's still absent, the user hasn't saved or used the wrong section name — ask them to check before continuing.

## Step 4 — Run locally

```
uv run python <source>_pipeline.py
```

Report what table was created and how many rows loaded (visible in output).

Then open the local data viewer:

```
uv run dlthub local show
```

This opens the dltHub local UI where the user can browse the loaded rows in DuckDB.

---

## If the job fails

Fix the pipeline file and re-run from Step 4.

| Symptom | Likely cause | Fix |
|---|---|---|
| 0 rows loaded | Wrong `data_selector` | Check raw response shape in output; update key or omit entirely |
| 401 / 403 error | Auth misconfigured | Verify credential is in `secrets.toml` (not `dev.secrets.toml`) and header name/location are correct |
| Script runs indefinitely | Paginator looping | Add `"paginator": "single_page"` to the resource's `endpoint` config |
| `ConfigFieldMissingException` | Secret key path mismatch | Check that `dlt.secrets["sources.<source>.<field>"]` matches the `[sources.<source>]` section in `secrets.toml` |
| `from dlt.hub import run` error | `dlt[hub]` not installed | Run `uv add "dlt[hub]"` |