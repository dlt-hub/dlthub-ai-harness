# NEVER change job resources without explicit human permission

`require.instance.size`, `execute.timeout` and trigger cadence spend the organization's run-time budget on **every run, forever**.

1. **Ask first, every time**, even when a job is OOM-killed, timing out or the user said "make it work". Show the budget math in the question (wall-clock hours × instance multiplier × runs, current vs proposed) and wait for an explicit yes. One yes covers one change to one job.
2. **Never bundle** a resource change into a deploy with other edits.
3. **Tune before you spend**: the **performance** toolkit (`optimize-performance`) first. The checks, the math and how to apply a change are in `instance-sizing.md` of `deploy-workspace`.

**Reference** https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size
