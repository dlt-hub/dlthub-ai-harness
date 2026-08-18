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
   current tiers and multipliers from `deploy-workspace` (`advanced-patterns.md`) or the reference below —
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
