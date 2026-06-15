---
name: test-deployment
description: Deploy the GitHub pipeline to dltHub Platform as a test run. Use when the user has seen their data locally and wants to deploy to the cloud.
argument-hint: ""
---

Deploy `github_pipeline.py` to dltHub Platform. This is a test deployment — the pipeline keeps the 50-row limit throughout. The goal is to verify the pipeline runs end-to-end on the cloud, not to do a full load.

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments

## Step 0 — Verify workspace connection

```bash
uv run dlthub workspace list
```

If no workspace is connected, connect the playground workspace:

```bash
uv run dlthub workspace connect playground
```

Once connected, continue to Step 1.

## Step 1 — Set up a cloud destination

The pipeline currently loads into `duckdb`, which only works locally. A cloud destination is required for data to persist on the platform.

**Reference**: https://dlthub.com/docs/general-usage/destination

Ask the user which destination they want to use:

| Destination | Package |
|---|---|
| MotherDuck | `uv add "dlt[motherduck]"` |
| BigQuery | `uv add "dlt[bigquery]"` |
| Snowflake | `uv add "dlt[snowflake]"` |
| Redshift | `uv add "dlt[redshift]"` |

Set up a named destination called `warehouse`. Check `config.toml` first — if a `[destination.warehouse]` block already exists there, move it to `dev.config.toml` so it only applies locally.

Write the prod credential skeleton using `secrets_update_fragment` with `path=".dlt/prod.secrets.toml"`:

```toml
[destination.warehouse]
destination_type = "<chosen-destination>"

[destination.warehouse.credentials]
database = ""
token = ""
```

Then tell the user:

> I've created the credential structure in `.dlt/prod.secrets.toml`. Please open that file and fill in your values, then let me know when done.

**Stop and wait** for the user to confirm before continuing.

Use `secrets_view_redacted` to verify — confirm credentials appear as `***`. If any field is still empty, ask the user to fill it in before proceeding.

Install the destination package and sync:

```bash
uv add "dlt[<extra>]"
uv sync
```

## Step 2 — Update destination in pipeline file

Change `destination="duckdb"` to the named destination in `github_pipeline.py`:

```python
pipeline = dlt.pipeline(
    pipeline_name="github_pipeline",
    destination="warehouse",
    dataset_name="github",
)
```

The `.add_limit(50, count_rows=True)` stays — this is a test deployment.

## Step 3 — Register in `__deployment__.py`

Add the pipeline to the existing `__deployment__.py`:

```python
from github_pipeline import load_github

__all__ = [..., "load_github"]
```

Preview what will change:

```bash
uv run dlthub deploy --dry-run
```

Show the user which jobs will be created or updated. **Stop and wait for approval** before proceeding.

## Step 4 — Deploy

```bash
uv run dlthub deploy
```

Summarize which jobs were created or updated.

## Step 5 — Run on the cloud

```bash
uv run dlthub run load_github -f
```

The `-f` flag streams logs in real time. Wait for the job to complete.

If it fails:

```bash
uv run dlthub job logs load_github
```

| Error | Cause | Fix |
|---|---|---|
| `Trial period has ended` | Plan expired | Contact your workspace admin |

Once successful, open the dltHub web UI:

```bash
uv run dlthub show
```