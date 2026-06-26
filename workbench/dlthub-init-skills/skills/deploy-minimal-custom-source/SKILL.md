---
name: deploy-minimal-custom-source
description: Build and deploy a minimal custom REST API pipeline to dltHub Platform. Use when the user says "Help me build and deploy a minimal pipeline".
argument-hint: "[source-name]"
---

# Build and deploy a minimal custom source

Build a minimal single-endpoint REST API pipeline and get it running on dltHub Platform as fast as possible. The 50-row limit stays throughout — this is a first-run cloud validation, not a full production load.

**Goal: fastest time to deployment. Every step must serve that goal.**

**References**:
- https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic
- https://dlthub.com/docs/hub/pipeline-operations/deployments
- https://dlthub.com/docs/hub/pipeline-operations/profiles

## DO NOT USE WHEN
- The data source is a SQL database or files — use `sql-database-pipeline` or `filesystem-pipeline` instead
- The user already has a working pipeline and wants to extend or harden it — use `rest-api-pipeline` instead
- The user wants a production-grade pipeline (auth, incremental, multiple endpoints) — use `rest-api-pipeline` instead

## Anti-patterns

These are the mistakes an agent makes without this skill. Avoid them:

- ❌ **Reading any `*.secrets.toml` file directly** — this is NEVER allowed. Reading `.dlt/secrets.toml`, `.dlt/dev.secrets.toml`, or `.dlt/prod.secrets.toml` with the Read tool dumps credential values (API keys, tokens, private keys) into the conversation context. Use `secrets_view_redacted` with `path=` instead — it shows `***` for all values.
- ❌ **Writing any `*.secrets.toml` file directly** — this is NEVER allowed. Never use the Write or Edit tool on any `*.secrets.toml` file. Use `secrets_update_fragment` with `path=` to write credential structure, and leave values empty (`""`) for the user to fill in.
- ❌ **`@dlt.resource` or a plain function** — not recognized as a platform job. Always use `@run.pipeline`.
- ❌ **`destination_type` written via `secrets_update_fragment`** — the MCP secrets tool normalizes `destination_type` to `type`, which the cloud runtime does not recognize. Always write `destination_type` directly to the profile config file (`.dlt/dev.config.toml` or `.dlt/prod.config.toml`) using the Edit tool.
- ❌ **Running `python <source>_pipeline.py` locally** — skip local runs; validate on the platform with the dev profile instead.
- ❌ **Running `uvx dlthub-init` as a bash command** — running it from within this session would interfere with the new workspace's AI assistance setup. Always tell the user to run it themselves in a separate terminal.

## Preconditions

Before starting, verify the workspace is ready:

```bash
uv run dlthub ai status
```

Confirm `__deployment__.py` exists in the project root — it is created by `uvx dlthub-init` and must be present before Step 8.

## Step 0 — Connect workspace

```bash
uv run dlthub workspace list
```

If a workspace is already connected and the user is happy with it, skip to Step 1.

Otherwise, connect to an existing workspace or create a new one:

```bash
uv run dlthub workspace connect                    # interactive — select or create
uv run dlthub workspace connect <name_or_id>       # connect directly by name or ID
uv run dlthub workspace connect <name_or_id> --org-id <id>  # specify org
```

**Stop and wait** for the user to confirm which workspace to use before continuing.

## Step 1 — Collect source and destination

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

## Step 2 — Research the API

Run 1–2 targeted web searches for the API's documentation. Extract only what is needed to write the pipeline:
- Base URL
- Authentication method and header/token format
- A single clear endpoint path
- The response wrapper key (e.g. `"data"`, `"items"`, or none if root array)

## Step 3 — Write the pipeline file

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

## Step 4 — Handle source credentials

**Never read or write `.dlt/secrets.toml` directly with Read/Write/Edit tools.**

Skip if the API is public.

Check first — use `secrets_view_redacted` (no `path=` needed for the default secrets file) to see if `[sources.<source>]` already exists. If it does and the value is `***`, skip this step.

Otherwise use `secrets_update_fragment` to write the skeleton:

```toml
[sources.<source>]
api_token = ""
```

Tell the user:
> I've added the credential structure to `.dlt/secrets.toml`. Please fill in your API token, then let me know when done.

**Stop and wait** for confirmation.

## Step 5 — Configure dev profile

`destination_type` is config, not a secret — write it directly to `.dlt/dev.config.toml`. Read the file first; if `[destination.warehouse]` already exists, skip.

Add to `.dlt/dev.config.toml`:

```toml
[destination.warehouse]
destination_type = "duckdb"
```

## Step 6 — Configure prod profile

Write `destination_type` directly to `.dlt/prod.config.toml`. Read the file first; if `[destination.warehouse]` already exists, skip.

Add to `.dlt/prod.config.toml`:

```toml
[destination.warehouse]
destination_type = "motherduck"  # or bigquery, snowflake, redshift
```

Then write **only the credentials** to `.dlt/prod.secrets.toml` using `secrets_update_fragment` with `path=".dlt/prod.secrets.toml"`. **Never use Write/Edit/Read on this file directly.**

```toml
[destination.warehouse.credentials]
database = ""
token = ""
```

Tell the user:
> I've added the credential structure to `.dlt/prod.secrets.toml`. Please fill in your values, then let me know when done.

**Stop and wait** for confirmation.

> **Note**: `.dlt/prod.secrets.toml` is not tracked by `secrets_list`. To verify without exposing values, use `secrets_view_redacted` with `path=".dlt/prod.secrets.toml"` — confirm credentials show as `***` before continuing. Never read this file on disk.

## Step 7 — Install destination package

```bash
uv add "dlt[<extra>]"
```

Use the package from the table in Step 1.

## Step 8 — Register and validate locally

Add the pipeline to `__deployment__.py`:

```python
from <source>_pipeline import load_<source>

__all__ = [..., "load_<source>"]
```

Run locally against DuckDB:

```bash
uv run dlthub local run --profile dev load_<source>
```

Run this **once**. Check the exit code and whether rows were reported loaded — that is sufficient. Do not re-run to capture more output or inspect full logs; every pipeline run costs API calls. If it succeeded, move on. If it failed, debug using the troubleshooting table below, fix, then run once more.

**Warnings are not failures.** Warnings about untyped columns, missing hints, or inferred schemas are expected on a first run and do not require investigation or a re-run. Only a non-zero exit code or zero rows loaded is a failure.

| Error | Fix |
|---|---|
| Job not recognized | Ensure `load_<source>` uses `@run.pipeline` and is listed in `__all__` |
| `Unknown DestinationModule` | Check `destination_type` is in `.dlt/dev.config.toml` or `.dlt/prod.config.toml`, not written via `secrets_update_fragment` |
| Auth / credential error | Use `secrets_view_redacted` with `path=".dlt/prod.secrets.toml"` to confirm credentials show as `***` |

## Step 9 — Deploy and run remotely

```bash
uv run dlthub deploy
uv run dlthub job run -f load_<source>
```

If it fails, inspect logs:

```bash
uv run dlthub job logs load_<source>
```

Once successful:

```bash
uv run dlthub show
```

## What's next?

Your pipeline is deployed and running on dltHub Platform.

You can now extend it using the **rest-api-pipeline** toolkit — for example:
- Add more endpoints to load additional resources from the same API
- Add incremental loading so only new or updated records are fetched on each run
- Add pagination to handle APIs that return large result sets across multiple pages

To continue, tell the agent: `"Help me extend my pipeline"`
