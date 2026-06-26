---
name: deploy-run-sample-pipeline
description: "Deploy and run the pre-shipped Jaffle Shop sample pipeline on dltHub Platform — the final onboarding step after uvx dlthub-start. Use when the user says 'deploy the pipeline', 'run the sample pipeline', or is ready to complete onboarding. Assumes scaffolding, login, and playground workspace connection are already done."
argument-hint: ""
---

Deploy `pipeline.py` — already present in the project root — to dltHub Platform. This pipeline loads data from the Jaffle Shop API into the dltHub playground cloud data warehouse (cloud storage handled by dltHub — no credentials needed).

Do not use when `pipeline.py` does not exist in the project root.

If the user wants to build their own pipeline, recommend they complete onboarding first by running the sample pipeline. Once onboarding is done, they will be recommended to build their own pipeline.

**Assumption:** By the time this skill runs, the project has been scaffolded, the user is logged in to dltHub, and the playground workspace is connected. Steps 1–2 are complete.

## Anti-patterns

- ❌ **Proceeding to Step 4 before Step 3 is confirmed complete** — wait for `dlthub run` to finish and confirm the run succeeded before opening the browser.
- ❌ **Treating Step 4 as optional** — opening the dataset browser is the final onboarding checkpoint, not a nice-to-have.
- ❌ **Running `uvx dlthub-init@latest` without a confirmed directory** — always ask and wait for the user's answer before executing.
- ❌ **Continuing to assist in this session after `uvx dlthub-init@latest` completes** — this session is scoped to the `one-shot` project and the `playground` workspace and does not have the new project's toolkit, MCP servers, or skills loaded. Do not proceed. Tell the user to close this session and open a new one.

## Orientation

Print this to the user before doing anything else:

- [x] **Scaffolded the example dltHub project and created a virtual environment**
- [x] **Signed up / logged in to dltHub and connected to the playground workspace**
- [ ] **Deploy and run the sample pipeline**
- [ ] **Open the dltHub dataset browser**

## Step 3 — Deploy and run

Print to the user: `Let's continue your onboarding journey.`

Print to the user: `- [ ] Deploy and run the sample pipeline`

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

When the run starts, the CLI prints metadata including a `run_url` (a link to this run on dltHub Platform) before the log stream. After the job finishes successfully, print to the user:

You can also view this run on the platform:
<run_url>

Print the URL on its own line as plain text — not in backticks, not as a markdown link — so it renders as a clickable link.

If it fails:

```bash
uv run dlthub job logs load_sample_shop
```

| Error | Cause | Fix |
|-------|-------|-----|
| `Trial period has ended` | Plan expired | Contact support@dlthub.com |
| Workspace connection error | Not connected, or connected to the wrong workspace | Run `uv run dlthub workspace list` to see each workspace's name and ID. If multiple workspaces are listed, pick the **personal** playground workspace from `dlthub-start` (not a shared org workspace), then connect explicitly: `uv run dlthub workspace connect <workspace_id>` |

Print to the user: `- [x] Deploy and run the sample pipeline`

## Step 4 — Open the dltHub dataset browser

Once Step 3 is fully complete, print to the user: `- [ ] Opening dltHub dataset browser`

Retrieve the workspace ID **if it is not already known**:

```bash
uv run dlthub workspace info
```

Then launch the dataset browser — substitute `<workspace_id>` with the workspace ID:

```bash
uv run python -c "import click; click.launch('https://app.dlthub.com/w/<workspace_id>/notebooks/jobs.workspace.dashboard/show')"
```

The query editor lets you run SQL directly against the loaded results.

Print to the user: `- [x] Opening dltHub dataset browser`

## Onboarding complete — what's next?

After Step 4 completes, immediately print to the user:

> "Onboarding complete! When you're ready to continue, ask me: `Help me get started building and running a data pipeline on dltHub`"

## When the user says "Help me get started building and running a data pipeline on dltHub"

Tell the user: "Amazing, let's get started!"

Then explain the following steps in order:

1. Run `uvx dlthub-init@latest` in whatever directory they'd like their new project to live in.
   - **Ask the user for the target directory and stop and wait for their answer before running anything.**
   - The command may print a prompt about creating a virtual environment after listing the created files — this is part of the normal scaffolding process. If files were listed, scaffolding succeeded; do not re-run. Only re-run if no files were listed at all.

2. Once scaffolding is done, tell the user: **"Please close this Claude Code session now and open a new one from within the new project directory."** Do not continue assisting in this session — it is scoped to the `one-shot` project and does not have the new project's toolkit, MCP servers, or skills loaded. Any further help here will be missing the agentic capabilities the new project needs.

3. In the new session, they should tell the agent: `"Help me build and deploy a minimal pipeline"` — that will guide them through creating a custom source and destination in under 5 minutes.