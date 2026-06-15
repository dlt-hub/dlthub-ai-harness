---
name: deploy-run-sample-pipeline
description: Write, deploy and run a GitHub issues pipeline on dltHub Platform. Use when the user wants to load GitHub issues from dlt-hub/dlt and deploy the pipeline to the cloud.
argument-hint: ""
---

Write a pipeline that loads the 50 most recent issues from `dlt-hub/dlt` and deploy it to dltHub Platform.

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments

## Step 1 — Write the pipeline file

Create `github_pipeline.py` in the project root:

```python
"""GitHub dlt pipeline.

Loads the 50 most recent issues from dlt-hub/dlt into DuckDB.
"""

import dlt
from dlt.sources.rest_api import rest_api_source
from dlt.hub import run


def github():
    return rest_api_source(
        {
            "client": {
                "base_url": "https://api.github.com/",
            },
            "resources": [
                {
                    "name": "issues",
                    "endpoint": {
                        "path": "repos/dlt-hub/dlt/issues",
                        "params": {
                            "state": "all",
                            "sort": "created",
                            "direction": "desc",
                        },
                    },
                    "primary_key": "id",
                },
            ],
        }
    )


@run.pipeline("github_pipeline")
def load_github():
    """Load the 50 most recent issues from dlt-hub/dlt."""

    pipeline = dlt.pipeline(
        pipeline_name="github_pipeline",
        destination="duckdb",
        dataset_name="github",
    )

    load_info = pipeline.run(github().add_limit(50, count_rows=True), write_disposition="replace")
    print(load_info)


if __name__ == "__main__":
    load_github()
```

## Step 2 — Verify workspace connection

```bash
dlthub workspace list
```

If no workspace is connected, connect the playground workspace:

```bash
dlthub workspace connect playground
```

## Step 3 — Set up a cloud destination

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

## Step 4 — Update destination in pipeline file

Change `destination="duckdb"` to the named destination in `github_pipeline.py`:

```python
pipeline = dlt.pipeline(
    pipeline_name="github_pipeline",
    destination="warehouse",
    dataset_name="github",
)
```

## Step 5 — Register in `__deployment__.py`

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

## Step 6 — Deploy

```bash
dlthub deploy
```

Summarize which jobs were created or updated.

## Step 7 — Run on the cloud

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
