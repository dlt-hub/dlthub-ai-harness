---
name: deploy-run-sample-pipeline
description: "Deploy and run the pre-shipped Jaffle Shop sample pipeline on dltHub Platform — an educational end-to-end run after uvx dlthub-start, NOT a production-grade pipeline. Use when the user wants to complete the onboarding deploy-and-run flow with the bundled pipeline.py. Assumes scaffolding, login, and playground workspace connection are already done."
argument-hint: ""
---

Deploy `pipeline.py` — already present in the project root — to dltHub Platform. This pipeline loads data from the Jaffle Shop API into the dltHub playground cloud data warehouse (cloud storage handled by dltHub — no credentials needed).

Do not use when `pipeline.py` does not exist in the project root.

If the user wants to build their own pipeline, recommend they complete onboarding first by running the sample pipeline. Once onboarding is done, they will be recommended to build their own pipeline.

**Assumption:** By the time this skill runs, the project has been scaffolded, the user is logged in to dltHub, and the playground workspace is connected. Steps 1–2 are complete.

## Orientation

Print this to the user before doing anything else:

- [x] **Scaffolded the example dltHub project and created a virtual environment**
- [x] **Signed up / logged in to dltHub and connected to the playground workspace**
- [ ] **Deploy and run the sample pipeline**
- [ ] **Open the dltHub dataset browser**

## Step 3 — Deploy and run

Print to the user: `- [ ] Step 3/4 — Deploy and run the sample pipeline`

**Deploy:**

```bash
uv run dlthub deploy
```

Summarize which jobs were created or updated.

**Run:**

```bash
uv run dlthub run load_sample_shop -f
```

The `-f` flag streams logs in real time. Wait for the job to complete.

If it fails:

```bash
uv run dlthub job logs load_sample_shop
```

| Error | Cause | Fix |
|-------|-------|-----|
| `Trial period has ended` | Plan expired | Contact support@dlthub.com |
| Workspace connection error | Not connected, or connected to the wrong workspace | Run `uv run dlthub workspace connect` and select the **personal** playground workspace — there may be more than one listed |

Print to the user: `- [x] Step 3/4`

## Step 4 — Open the dltHub dataset browser

Once Step 3 is fully complete, print to the user: `- [ ] Step 4/4 — Opening dltHub dataset browser`

Retrieve the workspace ID **if it is not already known**:

```bash
uv run dlthub workspace info
```

Then launch the dataset browser — substitute `<workspace_id>` with the workspace ID:

```bash
uv run python -c "import click; click.launch('https://app.dlthub.com/w/<workspace_id>/notebooks/jobs.workspace.dashboard/show')"
```

The query editor lets you run SQL directly against the loaded results.

Print to the user: `- [x] Step 4/4`

## Onboarding complete — what's next?

After Step 4 completes (dashboard opened), immediately print to the user:

> "Onboarding complete! When you're done exploring your data on the notebook, the next step is to build your own pipeline. Run `uvx dlthub-init` in a **new, separate directory** to scaffold a fresh dltHub project — it sets up `pyproject.toml`, the `uv.lock` lockfile, and the `.dlt/` config folder. Would you like me to walk you through it?"