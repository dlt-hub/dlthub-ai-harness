# Job resources and run-time budget

Runner size, timeout, and schedule cadence all spend your organization's **run-time budget**. They are
paid on **every run, forever** — unlike a code or config change, which is free.

**Charged budget = wall-clock hours × instance multiplier × runs.**

| Size | vCPU | Memory | Disk | Budget multiplier |
|---|---|---|---|---|
| `small` (default) | 2 | 4 GiB | 500 GB | 1× |
| `medium` | 4 | 8 GiB | 500 GB | 2× |
| `large` | 8 | 16 GiB | 500 GB | 4× |
| `xlarge` | 16 | 32 GiB | 500 GB | 8× |

1. Set via decorator only — `require={"instance": {"size": "medium"}}` on `@run.pipeline` / `@run.job` /
   `@run.interactive`. There is **no** toml or env-var form. Takes effect only after `dlthub deploy`.
2. Omitting `instance` means `small`. One hour on `large` spends four hours of budget.
3. **Disk is 500 GB on every tier** — sizing up never fixes `OSError: [Errno 28] No space left on device`.
4. Timeout (`execute={"timeout": "6h"}`, default 120 min) raises the *ceiling* on billable wall-clock;
   cadence (`trigger`) multiplies the number of billed runs. Both move budget as directly as size does.
5. **Break-even:** `small` → `medium` (2×) only stays budget-neutral if wall-clock drops by **≥50%**.
   A bigger box that does not roughly halve the run is a net budget **loss** — more resources, more spend,
   same or worse throughput.

# NEVER change job resources without explicit human permission

`require.instance.size`, `execute.timeout`, and trigger cadence are **budget-spending** parameters.

1. **ASK FIRST — every time.** Never add, raise, or lower these on the user's behalf, not even when a job
   is OOM-killed, timing out, or obviously slow, and not even when the user asked you to "make it work" or
   "fix the job". Diagnosing and *proposing* is your job; committing the spend is the user's.
2. **Show the budget math in the question**, so the user is deciding with the number in front of them:
   current size and multiplier → proposed size and multiplier, typical wall-clock per run, cadence, and the
   resulting change in charged hours per run and per month.
3. **Wait for an explicit yes.** Silence, "sounds good", or a general go-ahead given earlier in the session
   for unrelated work is not permission for this. Approval covers **one** change to **one** job — re-ask for
   the next tier, the next job, or a later session.
4. **Never bundle it in.** Do not slip a size or timeout change into a `dlthub deploy` alongside other
   edits. If you have unapproved resource changes staged, stop and ask before deploying.
5. **Tune before you spend.** A resource bump is the last resort, after the pipeline itself is tuned — hand
   over to the **performance** toolkit (`optimize-performance`, Step 4) to find the real bottleneck and check
   its gate. Install if absent: `uv run dlthub --non-interactive ai toolkit install performance`.
6. **Report what it cost.** After an approved change is deployed, read `dlthub job logs <name>` and tell the
   user whether the run actually got faster/fitted in memory, and recommend dropping back a tier if the
   multiplier is not earning itself.

**Reference** https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size
