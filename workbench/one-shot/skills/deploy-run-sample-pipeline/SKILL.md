---
name: deploy-run-sample-pipeline
description: "Test-deploy and run the pre-shipped GitHub issues sample pipeline on dltHub Platform — an educational end-to-end run to try dlthub and see a job on the cloud, NOT a production-grade pipeline. Use when the user wants to try/demo the deploy-and-run flow with the bundled github_pipeline.py. For a real pipeline (your own source, auth, incremental, custom destination, production deploy), use the rest-api-pipeline toolkit (find-source)."
argument-hint: ""
---

Deploy `github_pipeline.py` — already present in the project root — to dltHub Platform. This pipeline loads the 50 most recent issues from `dlt-hub/dlt`. Uses the built-in managed destination (cloud storage handled by dltHub — no credentials needed).

Do not use when the user wants to deploy a pipeline other than `github_pipeline.py`, or when `github_pipeline.py` does not already exist in the project root.

**Scope:** this is a throwaway, educational path for trying dlthub end-to-end. The moment the user wants a real pipeline — their own source, auth beyond a single key, incremental loading, multiple endpoints — hand over to the **rest-api-pipeline** toolkit (`find-source`); don't harden this sample in place.

## Orientation

Print this to the user before doing anything else:

- [ ] **Step 1 — Connect to playground workspace**
- [ ] Step 2 — Register the pipeline
- [ ] Step 3 — Deploy to the cloud
- [ ] Step 4 — Run the pipeline
- [ ] Step 5 — Open the results dashboard

Then ask the user: "Shall I start with Step 1?"

Wait for confirmation before proceeding. If the user says no or wants to do something else, stop and ask what they'd like to do instead.

## Step 1 — Connect to the personal playground workspace (a pre-configured sandbox for testing)

Print to the user: `- [ ] Step 1/5 — Connect to playground workspace`

```bash
uv run dlthub workspace connect playground
```

If multiple workspaces named `playground` exist, run `uv run dlthub workspace list` first, pick the personal one (not org-level), then connect to it by name.

Note the workspace ID from the output — you will need it in the final step.

Print to the user: "- [x] Step 1/5"

## Step 2 — Register in `__deployment__.py`

Print to the user: `- [ ] Step 2/5 — Register the pipeline`

Add the pipeline to the existing `__deployment__.py`:

```python
from github_pipeline import load_github

__all__ = ["load_github"]
```

Print to the user: "- [x] Step 2/5"

## Step 3 — Deploy

Print to the user: `- [ ] Step 3/5 — Deploy to the cloud`

```bash
uv run dlthub deploy
```

Summarize which jobs were created or updated.

Print to the user: "- [x] Step 3/5"

## Step 4 — Run on the cloud

Print to the user: `- [ ] Step 4/5 — Run the pipeline`

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

Print to the user: "- [x] Step 4/5"

## Step 5 — Open the results dashboard

Print to the user: `- [ ] Step 5/5 — Open the results dashboard`

Open the dltHub dashboard directly in the user's browser and invite them to explore the data using the query editor. Substitute `<workspace_id>` with the workspace ID captured in Step 1:

```bash
uv run python -c "import click; click.launch('https://app.dlthub.com/w/<workspace_id>/notebooks/jobs.workspace.dashboard/show')"
```

After the browser opens, print to the user: `5/5 ✓`

**Onboarding complete!** Your pipeline ran on dltHub Platform. Explore the loaded data in the dashboard — the query editor lets you run SQL directly against the results.

Ready to build a real pipeline? Just describe what you want here in the chat, e.g. "I want to load my Stripe payment data into a database — invoices and subscriptions."