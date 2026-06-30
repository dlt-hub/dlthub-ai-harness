---
name: one-shot
description: "Test or try dlthub end to end with a minimal, row-limited single-endpoint pipeline on local DuckDB plus an educational test deploy. Use for a quick demo, onboarding, or trying dlthub — NOT production. DO NOT USE for a real or production pipeline (use rest-api-pipeline)."
---

Read SOUL.md — it defines who you are and how you operate in this workspace.

# One-shot workflow

## Workflow Entry
**ALWAYS** start with `deploy-run-sample-pipeline`. Invoke it immediately — do not ask for clarification.

## Core workflow
1. **Deploy run sample pipeline** (`deploy-run-sample-pipeline`) — set up a cloud destination, deploy the pre-shipped GitHub pipeline to dltHub Platform, and run it on the cloud.

This workflow has exactly one step.

## Handover To Other Toolkits

None — this workflow ends when the cloud run completes.
