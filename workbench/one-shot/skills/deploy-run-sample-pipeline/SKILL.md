---
name: deploy-run-sample-pipeline
description: Write, deploy and run a GitHub issues pipeline on dltHub Platform. Use when the user wants to load GitHub issues from dlt-hub/dlt and deploy the pipeline to the cloud.
argument-hint: ""
---

Deploy `github_pipeline.py` — already present in the project root — to dltHub Platform. This pipeline loads the 50 most recent issues from `dlt-hub/dlt`.

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments

## Step 1 — Verify workspace connection

```bash
dlthub workspace list
```

If no workspace is connected, connect the playground workspace:

```bash
dlthub workspace connect playground
```

## Step 2 — Set up a cloud destination

The pipeline loads into `duckdb` locally. A cloud destination is required for data to persist on the platform.

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

## Step 3 — Update destination in pipeline file

Change `destination="duckdb"` to the named destination in `github_pipeline.py`:

```python
pipeline = dlt.pipeline(
    pipeline_name="github_pipeline",
    destination="warehouse",
    dataset_name="github",
)
```

## Step 4 — Register in `__deployment__.py`

Add the pipeline to the existing `__deployment__.py`:

```python
from github_pipeline import load_github

__all__ = [..., "load_github"]
```

Preview what will change:

```bash
dlthub deploy --dry-run
```

Show the user which jobs will be created or updated. **Stop and wait for approval** before proceeding.

## Step 5 — Deploy

```bash
dlthub deploy
```

Summarize which jobs were created or updated.

## Step 6 — Run on the cloud

```bash
dlthub run load_github -f
```

The `-f` flag streams logs in real time. Wait for the job to complete.

If it fails:

```bash
dlthub job logs load_github
```

| Error | Cause | Fix |
|---|---|---|
| `Trial period has ended` | Plan expired | Contact your workspace admin |

Once successful, open the dltHub web UI:

```bash
dlthub show
```
