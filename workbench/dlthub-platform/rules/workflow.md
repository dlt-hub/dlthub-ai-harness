# Deploy to dltHub Platform

This is the platform toolkit of the workspace: when the user wants to deploy, schedule or run jobs in production, start at its workflow entry. Other toolkits write platform commands without a prefix (`deploy`, `job run`, `job logs`): here they are `dlthub` commands, for example `dlthub deploy` and `dlthub job logs`.

It owns `.dlthub/platform/` in the workspace. It keeps nothing there yet; deploy records, when there are any, go to `.dlthub/platform/deploy/<environment>/`.

## Workflow Entry
**ALWAYS** start with **Setup runtime** (`setup-runtime`) — ensure workspace, dependencies, and runtime login are ready

## Core workflow
1. **Prepare deployment** (`prepare-deployment`, local-workspace toolkit) — before the first deployment
2. **Deploy pipeline** (`deploy-workspace`) — prepare scripts for production, run the jobs locally (`run-local-jobs`), deploy, launch, schedule

## Extend and harden
3. **Debug deployment** (`debug-deployment`) — a deployed job run failed: check job status, view logs, diagnose
4. **Inspect failures unattended** (`job-inspector`) — background agent that diagnoses every future failure of a deployed job; how to declare it: "Background agents" in `advanced-patterns.md` of (`deploy-workspace`)
5. **Write a background agent** (`create-background-agent`) — a new `AGENT.md` for work that should run on its own after an event

## Handover to other toolkits

### Incoming (to dlthub-platform)

- From **data-exploration** — the notebook file exists: deploy it as an interactive job with `dlthub serve`.
- From **data-quality** — the deployment target is known: the pipeline script with embedded `@dq.with_checks` (Profile A), or the data quality script that `run-data-quality` wrote (Profile B).
- From **performance** — the bottleneck is diagnosed and the runner is the ceiling: follow `instance-sizing.md` in (`deploy-workspace`), with the user's explicit yes.

References:
* **Additional documentation** https://dlthub.com/docs/hub/llms.txt
* **Workspace deployment reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments.md
* **Runtime overview**: https://dlthub.com/docs/hub/pipeline-operations/overview.md
* **Background agents**: https://dlthub.com/docs/hub/agents/agent-definitions.md
