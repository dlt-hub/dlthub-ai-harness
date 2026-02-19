---
name: adjust-endpoint
description: Adjust a working dlt pipeline for production — remove dev limits, verify pagination, configure incremental loading, expand date ranges. Use when the user wants to remove .add_limit(), load more data, fix pagination, or set up incremental loading.
argument-hint: <pipeline_name>
---

# Adjust endpoint for production

Parse `$ARGUMENTS`:
- `pipeline_name` (required): the dlt pipeline name

## Critical rule: removing `.add_limit()` requires verified pagination

`.add_limit(1)` during development masks pagination problems — only one page is fetched, so a broken paginator never loops. Removing it without explicit pagination causes stuck pipelines.

**Before removing `.add_limit()`:**
1. Check every resource has an explicit `"paginator"` config. If any rely on auto-detection, add one first.
2. Use `debug-pipeline` with INFO logging for the first unlimited run to watch pagination progress and catch loops early.

### Real example: OpenAI Usage API

Pipeline worked with `.add_limit(1)`. After removing the limit, it hung forever — dlt's auto-detected paginator looped. Fix: added explicit `"paginator": {"type": "cursor", "cursor_path": "next_page", "cursor_param": "page"}`. Full load then completed in 5 seconds.
