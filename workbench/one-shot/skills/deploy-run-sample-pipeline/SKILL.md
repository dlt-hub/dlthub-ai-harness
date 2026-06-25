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

Scaffold a fresh minimal workspace in a new directory, then hand over to the `dlthub-init-skills` toolkit.

### 1. Pick a directory

Ask the user where to create the new project, or suggest a name like `my-pipeline`. Wait for confirmation.

### 2. Scaffold the workspace

Run `uvx dlthub-init@latest` non-interactively — it is AI-aware and requires no interaction:

```bash
uvx dlthub-init@latest <dir>
```

Change into that directory for all subsequent commands:

```bash
cd <dir>
```

Verify the workspace is ready:

```bash
uv run dlthub ai status
```

### 3. Install and enter dlthub-init-skills

```bash
uv run dlthub --non-interactive ai toolkit install dlthub-init-skills --branch feat/handover-after-onboarding
```

Then load the toolkit's workflow rule and entry skill, and immediately invoke `deploy-minimal-custom-source` — carry any source name the user may have mentioned as its argument.