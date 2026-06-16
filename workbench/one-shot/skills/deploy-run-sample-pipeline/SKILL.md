---
name: deploy-run-sample-pipeline
description: Deploy and run the existing GitHub issues pipeline to dltHub Platform using the managed destination.
argument-hint: ""
---

Deploy `github_pipeline.py` — already present in the project root — to dltHub Platform. This pipeline loads the 50 most recent issues from `dlt-hub/dlt`. Uses the built-in managed destination; no credential setup required.

Do not use when the user wants to deploy a pipeline other than `github_pipeline.py`, or when `github_pipeline.py` does not already exist in the project root.

## Step 1 — Connect to the personal playground workspace

```bash
uv run dlthub workspace connect playground
```

If multiple workspaces named `playground` exist, run `uv run dlthub workspace list` first, pick the personal one (not org-level), then connect to it by name.

Note the workspace ID from the output — you will need it in the final step.

## Step 2 — Register in `__deployment__.py`

Add the pipeline to the existing `__deployment__.py`:

```python
from github_pipeline import load_github

__all__ = ["load_github"]
```

## Step 3 — Deploy

```bash
uv run dlthub deploy
```

Summarize which jobs were created or updated.

## Step 4 — Run on the cloud

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

Once successful, open the dltHub dashboard directly in the user's browser and invite them to explore the data using the query editor. Substitute `<workspace_id>` with the workspace ID captured in Step 1:

```bash
uv run python -c "import click; click.launch('https://app.dlthub.com/w/<workspace_id>/notebooks/jobs.workspace.dashboard/show')"
```