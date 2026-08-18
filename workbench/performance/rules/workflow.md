# Performance tuning workflow

## Workflow Entry
**ALWAYS** start with **Optimize performance** (`optimize-performance`) SKILL — diagnose which stage (extract / normalize / load) is the bottleneck, then apply the matching lever

## Core workflow
1. **Diagnose** (`optimize-performance`) — enable `progress="log"`, inspect the trace, and identify the slow or memory-heavy stage
2. **Apply levers** (`optimize-performance`) — tune extract/normalize/load parallelism, workers, buffers, and file rotation; combine with the calling pipeline toolkit's source-specific optimize skill
3. **Re-measure** (`optimize-performance`) — re-run, compare stage durations and peak memory, change one lever at a time

## Extend and harden
4. **Scale the runner, last** (`optimize-performance`) — only for dltHub platform jobs, only after 1-3: if the measured ceiling is the runner's own RAM/vCPU, pass the gates in Step 4 and raise `require={"instance": {"size": ...}}`. **NEVER change instance size or `execute.timeout` without explicit user permission** — it spends the organization's run-time budget by a multiplier on every run, so always propose it with the budget math and wait for a yes.

## Handover to other toolkits

### Incoming (to performance)

- From **rest-api-pipeline** (after `optimize-rest-api-performance`) — the pipeline and symptom are known; apply the source-agnostic stage levers on top of the REST-specific tuning.
- From **sql-database-pipeline** (after `optimize-sql-performance`) — the pipeline and symptom are known; apply the stage levers on top of the backend/`chunk_size` tuning.
- From **filesystem-pipeline** (after `optimize-filesystem-performance`) — the pipeline and symptom are known; apply the stage levers on top of the file-format/reader tuning.

### Outgoing (from performance)

- **rest-api-pipeline** — from (`optimize-performance`), for REST-specific extraction tuning (async resources, concurrency, page size); install the toolkit if absent, then start at `optimize-rest-api-performance`.
- **sql-database-pipeline** — from (`optimize-performance`), for database-specific tuning (backend, `chunk_size`, parallel tables, reflection); install the toolkit if absent, then start at `optimize-sql-performance`.
- **filesystem-pipeline** — from (`optimize-performance`), for file-specific tuning (reader, chunked streaming, glob narrowing); install the toolkit if absent, then start at `optimize-filesystem-performance`.
- **dlthub-platform** — from (`optimize-performance`), when the pipeline is tuned and stable and the user wants to deploy or schedule it on dltHub; start at `setup-runtime`.
- **dlthub-platform** — from (`optimize-performance`) Step 4, when the tuned job needs a larger instance size or a longer `execute` timeout; the manifest edit and `dlthub deploy` happen there — start at `deploy-workspace`.
