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
- ❌ **`destination_type` written via `secrets_update_fragment`** — the MCP secrets tool normalizes `destination_type` to `type`, which the cloud runtime does not recognize. Always write `destination_type` directly to the profile config file (`.dlt/dev.config.toml` or `.dlt/prod.config.toml`) using the Edit tool.
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

`destination_type` is config, not a secret — write it directly to `.dlt/dev.config.toml`. Read the file first; if `[destination.warehouse]` already exists, skip.

Add to `.dlt/dev.config.toml`:

```toml
[destination.warehouse]
destination_type = "duckdb"
```

## Step 5 — Configure prod profile

Write `destination_type` directly to `.dlt/prod.config.toml`. Read the file first; if `[destination.warehouse]` already exists, skip.

Add to `.dlt/prod.config.toml`:

```toml
[destination.warehouse]
destination_type = "motherduck"  # or bigquery, snowflake, redshift
```

Then write **only the credentials** to `.dlt/prod.secrets.toml` using `secrets_update_fragment` with `path=".dlt/prod.secrets.toml"`:

```toml
[destination.warehouse.credentials]
database = ""
token = ""
```

Tell the user:
> I've added the credential structure to `.dlt/prod.secrets.toml`. Please fill in your values, then let me know when done.

**Stop and wait** for confirmation.

> **Note**: `.dlt/prod.secrets.toml` is not tracked by `secrets_list`. To verify without exposing values, use `secrets_view_redacted` with `path=".dlt/prod.secrets.toml"` — confirm credentials show as `***` before continuing.

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

**Phase 1 — Run locally against DuckDB (quick validation):**

```bash
uv run dlthub local run --profile dev load_<source>
```

Do not proceed until this succeeds and reports rows loaded.

**Phase 2 — Run locally against your cloud destination (pre-flight check):**

```bash
uv run dlthub local run --profile prod load_<source>
```

Do not proceed until this succeeds.

**Phase 3 — Deploy and run remotely:**

```bash
uv run dlthub deploy
uv run dlthub job run -f load_<source>
```

If any phase fails, inspect logs:

```bash
uv run dlthub job logs load_<source>
```

| Error | Fix |
|---|---|
| Job not recognized | Ensure `load_<source>` uses `@run.pipeline` and is listed in `__all__` |
| `Unknown DestinationModule` | Check `destination_type` is in `.dlt/dev.config.toml` or `.dlt/prod.config.toml`, not written via `secrets_update_fragment` |
| Auth / credential error | Use `secrets_view_redacted` with `path=".dlt/prod.secrets.toml"` to confirm credentials show as `***` |

Once successful:

```bash
uv run dlthub show
```
