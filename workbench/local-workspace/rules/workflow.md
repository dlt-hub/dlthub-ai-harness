# Jobs on this machine

## Workflow Entry
**ALWAYS** start with **Run local jobs** (`run-local-jobs`) SKILL — make the code a job, list it in `__deployment__.py` and run it with `dlthub local run`

## Core workflow
1. **Run local jobs** (`run-local-jobs`) — declare jobs, run and serve them on this machine, read the result, debug a failed job run, add triggers
2. **Test local jobs** (`test-local-jobs`) — tests on the `tests` profile: call a job, run it end to end, dry-run every job of `__deployment__.py`

## Extend and harden
3. **Prepare deployment** (`prepare-deployment`) — the production destination, the `prod` profile and the job declarations, before the first deployment. A platform toolkit may replace its steps 1–2 with its own data connection skill

## Handover to other toolkits

### Incoming (to local-workspace)
- From a platform toolkit — it depends on this toolkit and uses its skills before each deployment: declare the jobs, run them once on this machine, test them

### Outgoing (from local-workspace)
- a platform toolkit — when the jobs run on this machine and the user wants to deploy them: follow the workflow entry of the installed platform toolkit, carrying the job refs and the destination
