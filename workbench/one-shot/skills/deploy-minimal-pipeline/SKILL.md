---
name: deploy-minimal-pipeline
description: Deploy the minimal REST API pipeline to dltHub Platform. Use when the user has a working local pipeline from create-minimal-pipeline and wants to run it on the cloud. Assumes workspace setup, login, and deployment file are already in place — production destination credentials are configured here.
---

Deploy `<source>_pipeline.py` to dltHub Platform. The pipeline keeps the 50-row limit — this is a first-run cloud validation, not a full load. The only code change needed is swapping `destination="duckdb"` for a cloud destination.

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments.md

## Step 0 — Verify workspace connection

Check that the local workspace is connected to a dltHub Platform workspace:

```bash
dlthub workspace list
```

If no workspace is connected, connect one:

```bash
dlthub workspace connect              # interactive — lists available workspaces to pick from
dlthub workspace connect <name_or_id> # skip prompt if name is known
```

Once connected, continue to Step 1.

## Step 1 — Set up production destination

The pipeline currently loads into `duckdb`, which only works locally — the runtime's ephemeral storage is wiped after each job run. A cloud destination is required for data to persist.

**Reference**: https://dlthub.com/docs/general-usage/destination.md

### 1a. Choose a destination

Ask the user which cloud destination they want to use. If unsure, recommend **MotherDuck** — it is DuckDB-compatible and the simplest upgrade path from a local setup.

### 1b. Set up a named destination

A named destination acts as an alias that maps to `duckdb` in dev and to the cloud destination in prod — the pipeline code stays the same in both environments. Pick a name (e.g. `warehouse`).

Use `secrets_update_fragment` with `path=".dlt/prod.secrets.toml"` to write the credential skeleton for the chosen destination — use empty strings as placeholder values:

```toml
[destination.warehouse]
type = "motherduck"  # replace with the actual destination type

[destination.warehouse.credentials]
database = ""
token = ""
```

Then tell the user:

> I've created the credential structure in `.dlt/prod.secrets.toml`. Please open that file and fill in your `database` and `token` values, then let me know when done.

**Stop and wait** for the user to confirm before continuing.

Once confirmed, use `secrets_view_redacted` to verify the destination section is populated — confirm `[destination.warehouse]` credentials appear as `***`. If any field is still empty, ask the user to fill it in before proceeding.

## Step 2 — Update destination in pipeline file

Open `<source>_pipeline.py` and change `destination="duckdb"` to the named destination from Step 1:

```python
# Before
pipeline = dlt.pipeline(
    pipeline_name="<source>_pipeline",
    destination="duckdb",
    dataset_name="<source>",
)

# After
pipeline = dlt.pipeline(
    pipeline_name="<source>_pipeline",
    destination="warehouse",  # named destination from Step 1
    dataset_name="<source>",
)
```

The `.add_limit(50, count_rows=True)` stays — this is a cloud validation run, not a full load.

## Step 3 — Register in `__deployment__.py`

Add the pipeline to the existing `__deployment__.py`:

1. Import the decorated function:
```python
from <source>_pipeline import load_<source>
```

2. Add it to `__all__`:
```python
__all__ = [..., "load_<source>"]
```

Preview what will change:
```bash
dlthub deploy --dry-run
```

Show the user which jobs will be created or updated. **Stop and wait for approval** before proceeding.

## Step 4 — Deploy

```bash
dlthub deploy
```

Summarize the output — which jobs were created or updated.

## Step 5 — Simulate locally with prod credentials

Before running on the cloud, simulate the job with production credentials:

```bash
dlthub local run load_<source> --profile prod
```

This runs the pipeline on your machine using production secrets and destination. Fix any credential or destination errors here before they reach the cloud.

## Step 6 — Run on the cloud

```bash
dlthub run load_<source> -f
```

The `-f` flag streams logs in real-time. Wait for the job to complete.

If it fails:
```bash
dlthub job logs load_<source>
```

| Error | Cause | Fix                        |
|---|---|----------------------------|
| `Trial period has ended` | Billing issue — your organization's plan has expired | Please pay to move forward |

Once successful, open the dltHub web UI to confirm the pipeline is live:
```bash
dlthub show
```