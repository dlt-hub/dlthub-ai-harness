---
name: deploy-run-sample-pipeline
description: "Test-deploy and run the pre-shipped GitHub issues sample pipeline on dltHub Platform — an educational end-to-end run to try dlthub and see a job on the cloud, NOT a production-grade pipeline. Use when the user wants to try/demo the deploy-and-run flow with the bundled github_pipeline.py. For a real pipeline (your own source, auth, incremental, custom destination, production deploy), use the rest-api-pipeline toolkit (find-source)."
argument-hint: ""
---

Deploy `github_pipeline.py` — already present in the project root — to dltHub Platform. This pipeline loads the 50 most recent issues from `dlt-hub/dlt`. Uses the built-in managed destination; no credential setup required.

Do not use when the user wants to deploy a pipeline other than `github_pipeline.py`, or when `github_pipeline.py` does not already exist in the project root.

**Scope:** this is a throwaway, educational path for trying dlthub end-to-end. The moment the user wants a real pipeline — their own source, auth beyond a single key, incremental loading, multiple endpoints — hand over to the **rest-api-pipeline** toolkit (`find-source`); don't harden this sample in place.

## Pre-execution check

**MANDATORY before doing anything else:** verify that `github_pipeline.py` exists in the project root.

If it does not exist, stop and tell the user:
> `github_pipeline.py` was not found in the project root. This skill only works with the pre-shipped sample pipeline. If you want to deploy your own pipeline, use the **rest-api-pipeline** toolkit instead (`find-source`).

Do not proceed past this point if the file is missing.

## Orientation

Print this to the user before doing anything else:

- [ ] Step 1 — Connect to playground workspace
- [ ] Step 2 — Register the pipeline
- [ ] Step 3 — Deploy to the cloud
- [ ] Step 4 — Run the pipeline
- [ ] Step 5 — Open the results dashboard

## Step 1 — Connect to the personal playground workspace

Print to the user:
- [ ] **Step 1 — Connect to playground workspace**
- [ ] Step 2 — Register the pipeline

```bash
uv run dlthub workspace connect playground
```

If multiple workspaces named `playground` exist, run `uv run dlthub workspace list` first, pick the personal one (not org-level), then connect to it by name.

Note the workspace ID from the output — you will need it in the final step.

## Step 2 — Register in `__deployment__.py`

Print to the user:
- [x] Step 1 — Connect to playground workspace
- [ ] **Step 2 — Register the pipeline**
- [ ] Step 3 — Deploy to the cloud

Add the pipeline to the existing `__deployment__.py`:

```python
from github_pipeline import load_github

__all__ = ["load_github"]
```

## Step 3 — Deploy

Print to the user:
- [x] Step 2 — Register the pipeline
- [ ] **Step 3 — Deploy to the cloud**
- [ ] Step 4 — Run the pipeline

```bash
uv run dlthub deploy
```

Summarize which jobs were created or updated.

## Step 4 — Run on the cloud

Print to the user:
- [x] Step 3 — Deploy to the cloud
- [ ] **Step 4 — Run the pipeline**
- [ ] Step 5 — Open the results dashboard

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

## Step 5 — Open the results dashboard

Print to the user:
- [x] Step 4 — Run the pipeline
- [ ] **Step 5 — Open the results dashboard**

Open the dltHub dashboard directly in the user's browser and invite them to explore the data using the query editor. Substitute `<workspace_id>` with the workspace ID captured in Step 1:

```bash
uv run python -c "import click; click.launch('https://app.dlthub.com/w/<workspace_id>/notebooks/jobs.workspace.dashboard/show')"
```

After the browser opens, print to the user:
- [x] Step 5 — Open the results dashboard

**Onboarding complete!** Your pipeline ran on dltHub Platform. Explore the loaded data in the dashboard — the query editor lets you run SQL directly against the results.

Ready to build a real pipeline — your own source, authentication, incremental loading? Hand over to the **rest-api-pipeline** toolkit (`find-source`).