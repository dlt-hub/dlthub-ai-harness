---
name: dlthub-platform-rules
description: "Always-on rules of the dltHub `dlthub-platform` toolkit: workflow order, conventions and constraints. Read it at the start of any work with the `dlthub-platform` toolkit and before using its skills. Codex plugins cannot ship always-loaded rules, so this skill carries them."
---

# NEVER change job resources without explicit human permission

`require.instance.size`, `execute.timeout`, and trigger cadence are **budget-spending** parameters: they
charge against the organization's run-time budget by a multiplier, on **every run, forever**. A code or
config change is free; these are not.

1. **ASK FIRST — every time.** Never add, raise, or lower these on the user's behalf, not even when a job
   is OOM-killed, timing out, or obviously slow, and not even when the user asked you to "make it work" or
   "fix the job". Diagnosing and *proposing* is your job; committing the spend is the user's.
2. **Show the budget math in the question**, so the user decides with the number in front of them: current
   vs proposed multiplier, typical wall-clock per run, cadence, and the resulting change in charged hours
   per run and per month. Charged budget = **wall-clock hours × instance multiplier × runs**. Read the
   current tiers and multipliers from `deploy-workspace` (`runtime-settings.md`) or the reference below —
   do not quote them from memory.
3. **Wait for an explicit yes.** Silence, "sounds good", or a general go-ahead given earlier in the session
   for unrelated work is not permission for this. Approval covers **one** change to **one** job — re-ask for
   the next tier, the next job, or a later session.
4. **Never bundle it in.** Do not slip a size or timeout change into a `dlthub deploy` alongside other
   edits. If you have unapproved resource changes staged, stop and ask before deploying.
5. **Tune before you spend.** A resource bump is the last resort, after the pipeline itself is tuned — hand
   over to the **performance** toolkit (`optimize-performance`, Step 4) for the real bottleneck, the gate
   that says whether hardware is genuinely the ceiling, and the break-even math. Install if absent:
   `uv run dlthub --non-interactive ai toolkit install performance`.
6. **Report what it cost.** After an approved change is deployed, read `dlthub job logs <name>` and tell the
   user whether the run actually got faster / fitted in memory, and recommend dropping back a tier if the
   multiplier is not earning itself.

Set via decorator only (`require={"instance": {"size": ...}}`), no toml or env-var form, and only in effect
after `dlthub deploy`. Omitting `instance` means the smallest tier.

**Reference** https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size

# Profiles
1. Locally pipelines and datasets run on `dev` profile.
2. On runtime pipelines (batch jobs) run on `prod` profile
3. On runtime notebooks (interactive jobs) run on `access` profile. if not defined they run on `prod` profile.
4. Agent jobs (`run.agent(...)`) **NEVER** run on `prod`. The runtime gives them the `access` profile when the deployment does not declare a profile: always pin `require={"profile": "access"}` so the declaration says so, and never override it with `prod`.
   The pin covers profile-scoped secrets only. A variable set with `--workspace` reaches every profile, so scope one an agent must not see with `--profile`. Work needing production write credentials goes in a pipeline or a plain job, not an agent.
5. If user pins a different profile - it is used to run pipelines and datasets locally.
6. Get workspace info (via cli or mcp tool) to see a list of profiles. **configured** profiles are one

# Secrets and configs
1. Profiles have corresponding secrets and configs.
2. `config.toml` and `secrets.toml` apply to **all profiles**. Keep only common settings in them
3. `dev.config.toml` and `dev.secrets.toml` define settings specific to `dev` profile
4. Settings in profile-scoped toml files overwrite workspace-scoped toml files.
5. Use `dlthub ai secrets` as usual — `update-fragment` requires `--path`, so always pass the right file! `dlthub ai secrets list` when in doubt.

# Switch profile
* set `WORKSPACE__PROFILE` env variable when running Python commands to temporarily switch profile
* pin profile with `dlthub local profile use <name>` to change profile in this session. **require to switch mcp server**

**Reference** https://dlthub.com/docs/hub/pipeline-operations/profiles.md

# Deploy to dltHub Platform

## Workflow Entry
**ALWAYS** start with **Setup runtime** (`setup-runtime`) — ensure workspace, dependencies, and runtime login are ready

## Core workflow
1. **Prepare workspace** (`prepare-deployment`) — split dev/prod credentials, set up production destination
2. **Deploy pipeline** (`deploy-workspace`) — prepare scripts for production, simulate job runs locally (`dlthub local run`/`serve`), deploy, launch, schedule

## Extend and harden
3. **Debug deployment** (`debug-deployment`) — check job status, view logs, diagnose failures
4. **Inspect failures unattended** (`job-inspector`) — background agent: runs after a job fails, reads the run record and the logs, follows the traceback into the workspace code, classifies the failure and proposes a fix naming the target and the change. Declare it with `run.agent("dlthub-platform:job-inspector", trigger=..., require={"profile": "access"})`, and set `AGENT__MODEL` in the workspace, at least as capable as Claude Sonnet 5. "Background agents" in (`deploy-workspace`) `advanced-patterns.md` says why each of those matters

## Handover to other toolkits

### Outgoing (from dlthub-platform)

- **rest-api-pipeline** → `debug-pipeline` / `adjust-endpoint` (modify existing) — when the user needs to build or modify a pipeline before deploying
- **data-exploration** → `build-notebook` — when the user wants to create marimo notebooks to deploy as interactive jobs
- **performance** → `optimize-performance` — when a deployed job is slow, OOM-killed, or hitting its timeout, *before* proposing a bigger instance size or a longer `execute.timeout`; those spend run-time budget on every run, so tune first (install if absent: `uv run dlthub --non-interactive ai toolkit install performance`)

### Incoming (to dlthub-platform)

- From **rest-api-pipeline** (after `debug-pipeline` or hardening steps) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` and `deploy-workspace` without re-discovery
- From **sql-database-pipeline** (after `create-sql-database-pipeline`, `debug-sql-database-pipeline`, `adjust-table`, or `add-table`) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` and `deploy-workspace` without re-discovery
- From **filesystem-pipeline** (after `create-filesystem-pipeline` or `add-incremental-loading`) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` without re-discovery
- From **transformations** (after `create-transformation` or `debug-transformation`) — transformation scripts and pipeline destination are already known; carry them into `setup-runtime`
- From **data-exploration** (after `build-notebook`) — notebook file already exists; `deploy-workspace` should use `dlthub serve` for the notebook job
- From **data-quality** Profile A (after `run-data-quality`) — pipeline script with embedded `@dq.with_checks` decorators is the deployment target; carry the pipeline script path, pipeline name, and destination into `setup-runtime`
- From **data-quality** Profile B (after `run-data-quality`) — `tools/dq_run.py` already exists with confirmed checks; carry the script path, pipeline name, and destination into `setup-runtime` as the deployment target
- From **performance** (after `optimize-performance` Step 4, with the user's explicit approval and budget math) — the bottleneck is diagnosed and the tier bump is agreed; apply `require={"instance": {"size": ...}}` in the manifest and `dlthub deploy`. Without that approval, route back to `optimize-performance`.
- From **quick-start** (shortcut path when a working pipeline exists) — pipeline name and destination may be inferred from `dlthub ai status`; `setup-runtime` runs full discovery if not.

References:
* **Additional documentation** https://dlthub.com/docs/hub/llms.txt
* **Workspace deployment reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments.md
* **Runtime overview**: https://dlthub.com/docs/hub/pipeline-operations/overview.md
