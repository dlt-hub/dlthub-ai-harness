---
name: deploy-minimal-custom-source
description: Build a minimal REST API pipeline and deploy it to dltHub Platform. Use when the user has just run uvx dlthub-init and wants to get a working pipeline running in the cloud. Covers source research, pipeline code, credentials, local validation, and cloud deployment end-to-end.
argument-hint: "[source-name]"
---

# Build and deploy a minimal custom source

Build a minimal single-endpoint REST API pipeline and get it running on dltHub Platform as fast as possible. The 50-row limit stays throughout — this is a first-run cloud validation, not a full production load.

**Goal: fastest time to deployment. Every step must serve that goal.**

**References**:
- https://dlthub.com/docs/general-usage/http/rest-client
- https://dlthub.com/docs/hub/pipeline-operations/deployments

## Step 0 — Identify the source

Parse `$ARGUMENTS` for a source name. If none was given, suggest three popular options (`github`, `hubspot`, `stripe_analytics`) or let the user name any REST API. Wait for their choice before proceeding.

## Step 1 — Research the API

Run 1–2 targeted web searches for the API's documentation. Extract only what is needed to write the pipeline:
- Base URL
- Authentication method and header/token format
- A single clear endpoint path
- The response wrapper key (e.g. `"data"`, `"items"`, or none if root array)

## Step 2 — Write the pipeline file

Create `<source>_pipeline.py` in the project root:

```python
import dlt
from dlt.sources.rest_api import rest_api_source

@dlt.resource(name="<resource_name>", primary_key="id")
def load_<resource_name>():
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
    yield from source

def load_<source>():
    pipeline = dlt.pipeline(
        pipeline_name="<source>_pipeline",
        destination="duckdb",
        dataset_name="<source>",
    )
    load_info = pipeline.run(
        load_<resource_name>().add_limit(50, count_rows=True)
    )
    print(load_info)

if __name__ == "__main__":
    load_<source>()
```

Rules:
- Always use `destination="duckdb"` at this stage
- Always keep `.add_limit(50, count_rows=True)`
- Omit `data_selector` if the response is a root JSON array
- Omit pagination config
- Adjust `primary_key` only if the API has an obvious unique field

## Step 3 — Handle credentials

Skip if the API is public.

Use `secrets_update_fragment` to write the skeleton into `.dlt/secrets.toml`:

```toml
[sources.<source>]
api_token = ""
```

Tell the user:
> I've added the credential structure to `.dlt/secrets.toml`. Please fill in your API token, then let me know when done.

**Stop and wait** for confirmation.

## Step 4 — Run locally

```bash
uv run python <source>_pipeline.py
```

Do not proceed until the run succeeds and reports rows loaded.

**Troubleshooting**:

| Issue | Fix |
|---|---|
| 0 rows | Check raw response; update `data_selector` or omit it |
| 401/403 | Verify `secrets.toml` path matches `dlt.secrets["..."]` key |
| Infinite run | Add `"paginator": "single_page"` to endpoint config |
| Import error | Run `uv add "dlt[hub]"` |

## Step 5 — Connect workspace

```bash
uv run dlthub workspace list
```

If no workspace is connected, connect to personal `playground`:

```bash
uv run dlthub workspace connect playground
```

## Step 6 — Set up production destination

The cloud runtime's storage is ephemeral — a cloud destination is required for data to persist.

**Reference**: https://dlthub.com/docs/general-usage/destination

Ask the user which cloud destination they want. If unsure, recommend **MotherDuck** — DuckDB-compatible, simplest path.

Write the credential skeleton using `secrets_update_fragment` with `path=".dlt/prod.secrets.toml"`:

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

Install the destination package:

| Destination | Command |
|---|---|
| MotherDuck | `uv add "dlt[motherduck]"` |
| BigQuery | `uv add "dlt[bigquery]"` |
| Snowflake | `uv add "dlt[snowflake]"` |
| Redshift | `uv add "dlt[redshift]"` |

## Step 7 — Update destination in pipeline file

Change `destination="duckdb"` to `"warehouse"` in `<source>_pipeline.py`. Keep `.add_limit(50, count_rows=True)`.

## Step 8 — Register, deploy, and run

Add the pipeline to `__deployment__.py`:

```python
from <source>_pipeline import load_<source>

__all__ = [..., "load_<source>"]
```

Deploy and run:

```bash
uv run dlthub deploy
uv run dlthub run load_<source> -f
```

If it fails:

```bash
uv run dlthub job logs load_<source>
```

Once successful:

```bash
uv run dlthub show
```
