# Performance tuning workflow

## Workflow Entry
**ALWAYS** start with **Optimize performance** (`optimize-performance`) SKILL — diagnose which stage (extract / normalize / load) is the bottleneck, then apply the matching lever

## Core workflow
1. **Diagnose** (`optimize-performance`) — enable `progress="log"`, inspect the trace (`dlthub local pipeline trace <pipeline_name> metrics` shows rows, files and sizes of each step), and identify the slow or memory-heavy stage
2. **Apply levers** (`optimize-performance`) — tune extract/normalize/load parallelism, workers, buffers, and file rotation; combine with the calling pipeline toolkit's source-specific optimize skill
3. **Re-measure** (`optimize-performance`) — re-run, compare stage durations and peak memory, change one lever at a time

## Extend and harden
4. **Scale the runner, last** (`optimize-performance`) — only for deployed jobs, only after 1-3, and never without the user's explicit yes

## Handover to other toolkits

### Incoming (to performance)

- From a pipeline toolkit's optimize skill (`optimize-rest-api-performance`, `optimize-sql-performance`, `optimize-filesystem-performance`) — the symptom and the source-specific levers already applied are known: tune the stages on top of them, and do not undo them.
