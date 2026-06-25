---
name: deploy-minimal-custom-source
description: Build and deploy a pipeline to dltHub Platform. Use when the user has just set up their dlthub workspace and wants to get a working pipeline running in the cloud for the first time.
argument-hint: "[source-name]"
---

# Build and deploy a minimal custom source

Build a minimal single-endpoint REST API pipeline and get it running on dltHub Platform as fast as possible. The 50-row limit stays throughout — this is a first-run cloud validation, not a full production load.

**Goal: fastest time to deployment. Every step must serve that goal.**

**References**:
- https://dlthub.com/docs/general-usage/http/rest-client
- https://dlthub.com/docs/hub/pipeline-operations/deployments
- https://dlthub.com/docs/hub/pipeline-operations/profiles

## DO NOT USE WHEN
- The data source is a SQL database or files — use `sql-database-pipeline` or `filesystem-pipeline` instead
- The user already has a working pipeline and wants to extend or harden it — use `rest-api-pipeline` instead
- The user wants a production-grade pipeline (auth, incremental, multiple endpoints) — use `rest-api-pipeline` instead

## Anti-patterns

These are the mistakes an agent makes without this skill. Avoid them:

- ❌ **`@dlt.resource` or a plain function** — not recognized as a platform job. Always use `@run.pipeline`.
- ❌ **`destination_type` in `config.toml`** — `dlthub deploy` won't sync it to the cloud runtime. Always write `destination_type` to the profile-specific secrets file (`.dlt/dev.secrets.toml` or `.dlt/prod.secrets.toml`).
- ❌ **Running `python <source>_pipeline.py` locally** — skip local runs; validate on the platform with the dev profile instead.

## Preconditions

Before starting, verify the workspace is ready:

```bash
uv run dlthub ai status
```

Also confirm `__deployment__.py` exists in the project root — it is created by `uvx dlthub-init` and must be present before Step 7.

## Step 0 — Collect source and destination

Ask the user two things upfront:

1. **Source**: which API do they want to load from? If not given, suggest `github`, `hubspot`, or `stripe_analytics`.
2. **Destination**: which cloud destination do they want for the prod profile? If unsure, recommend **MotherDuck** — DuckDB-compatible, simplest path.

| Destination | Package |
|---|---|
| MotherDuck | `dlt[motherduck]` |
| BigQuery | `dlt[bigquery]` |
| Snowflake | `dlt[snowflake]` |
| Redshift | `dlt[redshift]` |

Wait for both answers before proceeding.

## Step 1 — Research the API

Run 1–2 targeted web searches for the API's documentation. Extract only what is needed to write the pipeline:
- Base URL
- Authentication method and header/token format
- A single clear endpoint path
- The response wrapper key (e.g. `"data"`, `"items"`, or none if root array)

## Step 2 — Write the pipeline file

Create `<source>_pipeline.py` in the project root. Use `@run.pipeline` so the function is recognized as a job on dltHub Platform. Use `destination="warehouse"` — a named destination that maps to duckdb in dev and the cloud destination in prod.

```python
import dlt
from dlt.sources.rest_api import rest_api_source
from dlt.hub import run
from dlt.hub.run import trigger

@run.pipeline(
    "<source>_pipeline",
    trigger=trigger.every("1d"),
    expose={"tags": ["ingest"], "display_name": "<Source> ingest"},
)
def load_<source>():
    source = rest_api_source(
        {
            "client": {
                "base_url": "<base_url>",
                "auth": {
                    "type": "bearer",  # adjust to actual auth type
                    "token": dlt.secrets["sources.<source>.api_token"],
                },
            },
            "resources": [
                {
                    "name": "<resource_name>",
                    "endpoint": {
                        "path": "<endpoint_path>",
                        "data_selector": "<wrapper_key>",  # omit if root array
                    },
                }
            ],
        }
    )
    pipeline = dlt.pipeline(
        pipeline_name="<source>_pipeline",
        destination="warehouse",
        dataset_name="<source>",
    )
    pipeline.run(source.add_limit(50, count_rows=True))
```

Rules:
- Always keep `.add_limit(50, count_rows=True)` for the first validation run
- Omit `data_selector` if the response is a root JSON array
- Omit pagination config
- Adjust `primary_key` only if the API has an obvious unique field

## Step 3 — Handle source credentials

Skip if the API is public.

Check first — use `secrets_view_redacted` to see if `[sources.<source>]` already exists in `.dlt/secrets.toml`. If it does and the value is `***`, skip this step.

Otherwise use `secrets_update_fragment` to write the skeleton:

```toml
[sources.<source>]
api_token = ""
```

Tell the user:
> I've added the credential structure to `.dlt/secrets.toml`. Please fill in your API token, then let me know when done.

**Stop and wait** for confirmation.

## Step 4 — Configure dev profile

Write the dev destination (duckdb) to `.dlt/dev.secrets.toml`. Check first with `secrets_view_redacted` — if `[destination.warehouse]` already exists there, skip.

Use `secrets_update_fragment` with `path=".dlt/dev.secrets.toml"`:

```toml
[destination.warehouse]
destination_type = "duckdb"
```

## Step 5 — Configure prod profile

Write the full prod destination block to `.dlt/prod.secrets.toml`. Check first — open the file or use `secrets_view_redacted` with `path=".dlt/prod.secrets.toml"` if supported; if `[destination.warehouse]` already exists with values, skip.

Use `secrets_update_fragment` with `path=".dlt/prod.secrets.toml"`:

```toml
[destination.warehouse]
destination_type = "motherduck"  # or bigquery, snowflake, redshift

[destination.warehouse.credentials]
database = ""
token = ""
```

Tell the user:
> I've created the credential structure in `.dlt/prod.secrets.toml`. Please fill in your values, then let me know when done.

**Stop and wait** for confirmation.

> **Note**: `.dlt/prod.secrets.toml` is not tracked by `secrets_list` — verify the file directly on disk before continuing.

## Step 6 — Install destination package

```bash
uv add "dlt[<extra>]"
```

Use the package from the table in Step 0.

## Step 7 — Connect workspace

```bash
uv run dlthub workspace list
```

If no workspace is connected, connect to `playground`:

```bash
uv run dlthub workspace connect playground
```

## Step 8 — Register, deploy, and run

Add the pipeline to `__deployment__.py`:

```python
from <source>_pipeline import load_<source>

__all__ = [..., "load_<source>"]
```

Deploy, then run with the dev profile first (validates against duckdb on the cloud):

```bash
uv run dlthub deploy
uv run dlthub run load_<source> --profile dev -f
```

Once the dev run succeeds, run with the prod profile:

```bash
uv run dlthub run load_<source> --profile prod -f
```

If either run fails:

```bash
uv run dlthub job logs load_<source>
```

| Error | Fix |
|---|---|
| Job not recognized | Ensure `load_<source>` uses `@run.pipeline` and is in `__all__` |
| `Unknown DestinationModule` | Check `destination_type` is in the profile secrets file, not `config.toml` |
| Auth / credential error | Verify `.dlt/prod.secrets.toml` values are filled in on disk |

Once successful:

```bash
uv run dlthub show
```
