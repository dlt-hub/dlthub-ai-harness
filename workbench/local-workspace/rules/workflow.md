# Jobs on this machine

## Workflow Entry
**ALWAYS** start with **Run local jobs** (`run-local-jobs`) SKILL — make the code a job, list it in `__deployment__.py` and run it with `dlthub local run`

## Core workflow
1. **Run local jobs** (`run-local-jobs`) — declare jobs, run and serve them on this machine, read the result, debug a failed job run, add triggers
2. **Test local jobs** (`test-local-jobs`) — tests on the `tests` profile: call a job, run it end to end, dry-run every job of `__deployment__.py`

## Extend and harden
3. **Prepare deployment** (`prepare-deployment`) — the production destination, the `prod` profile and the job declarations, before the first deployment
