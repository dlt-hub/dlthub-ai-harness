# Deploy to dltHub Platform

This is the platform toolkit of the workspace: when the user wants to deploy, schedule or run jobs in production, start at its workflow entry. Other toolkits write platform commands without a prefix (`deploy`, `job run`, `job logs`): here they are `dlthub` commands, for example `dlthub deploy` and `dlthub job logs`.

It owns `.dlthub/platform/` in the workspace. It keeps nothing there yet; deploy records, when there are any, go to `.dlthub/platform/deploy/<environment>/`.

## Workflow Entry
**ALWAYS** start with **Prepare deployment** (`prepare-deployment`) of the local-workspace toolkit — check that the workspace is ready for a deployment; it sends you to (`define-and-debug-jobs`) for jobs, triggers and local debug runs that are missing

## Core workflow
1. **Prepare deployment** (`prepare-deployment`) of local-workspace — the readiness check, the production destination and the `prod` profile
2. **Set up the runtime** (`setup-runtime`) — `dlt[hub]`, the dltHub login and the remote workspace
3. **Deploy and run in production** (`deploy-workspace`) — deploy, launch; the triggers start running the jobs

## Extend and harden
4. **Debug deployment** (`debug-deployment`) — a deployed job run failed: check job status, view logs, diagnose
5. **Inspect failures unattended** (`job-inspector`) — background agent that diagnoses every future failure of a deployed job; how to declare it: "Background agents" in `advanced-patterns.md` of (`deploy-workspace`)
6. **Write a background agent** (`create-background-agent`) — a new `AGENT.md` for work that should run on its own after an event

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
