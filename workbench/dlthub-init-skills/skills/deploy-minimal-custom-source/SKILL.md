---
name: deploy-minimal-custom-source
description: Build a minimal REST API pipeline and deploy it to dltHub Platform. Use when the user has just run uvx dlthub-init and wants to get a working pipeline running in the cloud. Covers source research, pipeline code, credentials, local validation, and cloud deployment end-to-end.
argument-hint: "[source-name]"
---

# Build and deploy a minimal custom source

Build a minimal single-endpoint REST API pipeline locally against DuckDB, then deploy it to dltHub Platform. The 50-row limit stays throughout — this is a first-run cloud validation, not a full production load.

**References**:
- https://dlthub.com/docs/general-usage/http/rest-client
- https://dlthub.com/docs/hub/pipeline-operations/deployments

## Step 0 — Identify the source

Parse `$ARGUMENTS` for a source name. If none was given, suggest three popular options (`github`, `hubspot`, `stripe_analytics`) or let the user name any REST API. Wait for their choice before proceeding.

## Step 1 — Research the API

1. Check for verified dlt sources: `uv run dlthub --non-interactive pipeline init --list-sources`
2. If a verified source exists, tell the user and suggest `dlthub pipeline init <source> <destination>` — a pre-built connector is almost always better. Stop here unless the user explicitly wants to proceed with a custom pipeline.
3. Run 1–2 targeted web searches for the API's documentation. Extract:
   - Base URL
   - Authentication method and header/token format
   - A clear endpoint path to start with
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
- Adjust `primary_key` to the actual unique field

## Step 3 — Handle credentials

Skip this step if the API is public (no auth required).

1. Use `secrets_view_redacted` to check if credentials already exist
2. Use `secrets_update_fragment` to write a skeleton into `.dlt/secrets.toml`:

```toml
[sources.<source>]
api_token = ""
```

3. Tell the user:
> I've added the credential structure to `.dlt/secrets.toml`. Please fill in your API token, then let me know when done.

**Stop and wait** for the user to confirm before continuing.

4. Use `secrets_view_redacted` to verify the value shows as `***`.

## Step 4 — Run locally

```bash
uv run python <source>_pipeline.py
```

Then open the local UI (run in background):

```bash
uv run dlthub local show
```

**Troubleshooting**:

| Issue | Likely cause | Fix |
|---|---|---|
| 0 rows | Wrong `data_selector` | Check raw response; update key or omit |
| 401/403 | Auth misconfigured | Verify `secrets.toml` path and header format |
| Infinite run | Paginator looping | Add `"paginator": "single_page"` to endpoint config |
| `ConfigFieldMissingException` | Secret path mismatch | Match `dlt.secrets["..."]` path to `secrets.toml` key |
| Import error | Missing dependency | Run `uv add "dlt[hub]"` |

Do not proceed to deployment until the local run succeeds and rows appear in the UI.

## Step 5 — Connect workspace

```bash
dlthub workspace list
```

If no workspace is connected, connect to `playground` (recommended default for a first deploy):

```bash
dlthub workspace connect playground
```

## Step 6 — Set up production destination

The pipeline loads into `duckdb` locally, but the cloud runtime's storage is ephemeral — a cloud destination is required for data to persist.

**Reference**: https://dlthub.com/docs/general-usage/destination

### 6a. Choose a destination

Ask the user which cloud destination they want. If unsure, recommend **MotherDuck** — it is DuckDB-compatible and the simplest path from a local setup.

### 6b. Create a named destination

Check `config.toml` first. If a `[destination.warehouse]` block with `destination_type` already exists there, move it to `dev.config.toml` — use MCP secrets tools, never edit the files directly.

Write the prod credential skeleton using `secrets_update_fragment` with `path=".dlt/prod.secrets.toml"`:

```toml
[destination.warehouse]
destination_type = "motherduck"  # or bigquery, snowflake, redshift

[destination.warehouse.credentials]
database = ""
token = ""
```

Tell the user:
> I've created the credential structure in `.dlt/prod.secrets.toml`. Please fill in your values, then let me know when done.

**Stop and wait** for confirmation, then verify with `secrets_view_redacted` that credentials show as `***`.

### 6c. Install the destination package

| Destination | Command |
|---|---|
| MotherDuck | `uv add "dlt[motherduck]"` |
| BigQuery | `uv add "dlt[bigquery]"` |
| Snowflake | `uv add "dlt[snowflake]"` |
| Redshift | `uv add "dlt[redshift]"` |

```bash
uv add "dlt[<extra>]" && uv sync
```

## Step 7 — Update destination in pipeline file

Change `destination="duckdb"` to the named destination in `<source>_pipeline.py`:

```python
pipeline = dlt.pipeline(
    pipeline_name="<source>_pipeline",
    destination="warehouse",  # named destination from Step 6
    dataset_name="<source>",
)
```

Keep `.add_limit(50, count_rows=True)` — this cloud run is still a validation run.

## Step 8 — Register in `__deployment__.py`

Add the pipeline function to the existing `__deployment__.py`:

```python
from <source>_pipeline import load_<source>

__all__ = [..., "load_<source>"]
```

Preview what will be registered:

```bash
dlthub deploy --dry-run
```

Show the user which jobs will be created. **Stop and wait for approval** before running the real deploy.

## Step 9 — Deploy and run

```bash
dlthub deploy
```

Simulate locally with production credentials before hitting the cloud:

```bash
dlthub local run load_<source> --profile prod
```

Fix any credential or destination errors here. Then run on the cloud:

```bash
dlthub run load_<source> -f
```

`-f` streams logs in real-time. If it fails, inspect logs:

```bash
dlthub job logs load_<source>
```

Once successful, confirm the pipeline is live:

```bash
dlthub show
```
