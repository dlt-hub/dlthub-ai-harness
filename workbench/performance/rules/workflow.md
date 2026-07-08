# Performance tuning workflow

## Workflow Entry
**ALWAYS** start with **Optimize performance** (`optimize-performance`) SKILL — diagnose which stage (extract / normalize / load) is the bottleneck, then apply the matching lever

## Core workflow
1. **Diagnose** (`optimize-performance`) — enable `progress="log"`, inspect the trace, and identify the slow or memory-heavy stage
2. **Apply levers** (`optimize-performance`) — tune extract/normalize/load parallelism, workers, buffers, and file rotation; combine with the calling pipeline toolkit's source-specific optimize skill
3. **Re-measure** (`optimize-performance`) — re-run, compare stage durations and peak memory, change one lever at a time

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
