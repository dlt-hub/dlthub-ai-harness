---
name: deploy-run-sample-pipeline
description: "Deploy and run the pre-shipped Jaffle Shop sample pipeline on dltHub Platform — an educational end-to-end run after uvx dlthub-start, NOT a production-grade pipeline. Use when the user wants to complete the onboarding deploy-and-run flow with the bundled pipeline.py."
argument-hint: ""
---

Deploy `pipeline.py` — already present in the project root — to dltHub Platform. This pipeline loads data from the Jaffle Shop API into the dltHub playground cloud data warehouse (cloud storage handled by dltHub — no credentials needed).

Do not use when `pipeline.py` does not exist in the project root, or when the user wants to build their own pipeline rather than run the sample.

## Orientation

Print this to the user before doing anything else:

- [x] **Scaffolded the example dltHub project and created a virtual environment**
- [ ] **Log in to dltHub (or create a free trial account)**
- [ ] **Connect to the playground workspace**
- [ ] **Deploy and run the sample pipeline**
- [ ] **Build your own production pipeline or keep exploring**

Then ask the user: "Shall I start with Step 3?"

Wait for confirmation before proceeding. If the user says no or wants to do something else, stop and ask what they'd like to do instead.

## Step 3 — Log in

Print to the user: `- [ ] Step 3/6 — Log in to dltHub`

```bash
uv run dlthub login
```

This opens a browser link for authentication. Stream the output so the user sees the link and can click it. Wait for login to complete before proceeding.

Print to the user: `- [x] Step 3/6`

## Step 4 — Connect workspace

Print to the user: `- [ ] Step 4/6 — Connect to the playground workspace`

Check that a workspace is active:

```bash
uv run dlthub workspace info
```

Note the workspace ID from the output — you will need it in Step 6.

If the command errors or shows no active workspace, connect to the playground workspace:

```bash
uv run dlthub workspace connect playground
```

If multiple workspaces named `playground` exist, run `uv run dlthub workspace list` first, pick the personal one (not org-level), then connect to it by name. Note the workspace ID once connected.

Print to the user: `- [x] Step 4/6`

## Step 5 — Deploy and run

Print to the user: `- [ ] Step 5/6 — Deploy and run the sample pipeline`

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
| `Trial period has ended` | Plan expired | Contact your workspace admin |

Print to the user: `- [x] Step 5/6`

## Step 6 — Next steps

Print to the user: `- [ ] Step 6/6 — Build your own production pipeline or keep exploring`

**Onboarding complete!** Your pipeline ran on dltHub Platform. Open the dltHub dashboard directly in the user's browser — substitute `<workspace_id>` with the workspace ID captured in Step 4:

```bash
uv run python -c "import click; click.launch('https://app.dlthub.com/w/<workspace_id>/notebooks/jobs.workspace.dashboard/show')"
```

If the workspace ID wasn't captured earlier, retrieve it now:

```bash
uv run dlthub workspace info
```

The query editor lets you run SQL directly against the loaded results.

Ready to build a real pipeline? Just describe what you want, e.g. "I want to load my Stripe payment data into a database — invoices and subscriptions."