---
name: quick-start
description: "Use when the user wants a guided end-to-end run from data to dashboard in a few prompts: 'show me a demo', 'give me a quick start', 'take me through the full workflow', 'how do I go from data to dashboard', 'walk me through ingestion to visualization', 'I want to try everything end-to-end'.
  Do NOT use when the user is asking what's available or where to start in general — use the `toolkit-dispatch` skill (in init) for capability-discovery questions ('what can you do', 'what toolkits are there', 'I'm new to dlt').
  Do NOT use when the user already has a specific task underway (debugging, adding an endpoint, deploying)."
argument-hint: "[data-source] [path]"
---

# Quick Start

Guide the user from zero to a working demo in 3-5 prompts.

Parse `$ARGUMENTS`:
- `data-source` (optional): what the user wants to extract data from
- `path` (optional): one of `discover`, `inspect`, `production`, `cdm`

## Step 1 — Check workspace status

Run `uv run dlt ai status`.

- If everything is set up: continue to Step 2.
- If prerequisites are missing (no workspace, MCP not connected, missing dependencies): briefly tell the user what is missing in one line, then offer to run `/init-workspace` (from the **bootstrap** toolkit). Do not auto-install — wait for confirmation.

## Step 2 — Present capability index and ask one question

If `$ARGUMENTS` already has both source and path, skip to Step 3.

If the user has mentioned an existing pipeline (has data already loaded), route directly:
- wants to explore or visualize → invoke `explore-data`
- wants to model or transform → invoke `annotate-sources`
- wants to deploy → invoke `setup-runtime`

Otherwise, show the capability table and depth menu, then ask: **"What do you want to extract data from?"**

```
INGEST     → REST API pipelines (find-source → create → debug → validate)
EXPLORE    → Marimo dashboards (explore-data → build-notebook)
TRANSFORM  → Canonical data model — Kimball (annotate-sources → generate-cdm → create-transformation)
DEPLOY     → dltHub Runtime on a schedule (setup-runtime → prepare-deployment → deploy-workspace)

Pick a depth:
  [1] Discover    — ingest + visualize (3 prompts, great for demos)
  [2] Inspect     — ingest + validate schema/data + visualize (one inspection checkpoint)
  [3] Production  — ingest + validate + deploy + visualize
  [4] Full CDM    — ingest + validate + model + transform + visualize (~8 steps)

What do you want to extract data from?
```

If the user answers with just a source name, default to **Discover** unless they also pick a depth.

## Step 3 — Confirm path and hand off

Announce the step sequence for the chosen path, then invoke `find-source` with the source name.

| Path | Sequence |
|---|---|
| Discover | find-source → create-rest-api-pipeline → debug-pipeline → explore-data → build-notebook |
| Inspect | find-source → create-rest-api-pipeline → debug-pipeline → validate-data → explore-data → build-notebook |
| Production | find-source → create-rest-api-pipeline → debug-pipeline → validate-data → setup-runtime → prepare-deployment → deploy-workspace → explore-data → build-notebook |
| Full CDM | find-source → create-rest-api-pipeline → debug-pipeline → validate-data → annotate-sources → create-ontology → generate-cdm → create-transformation → explore-data → build-notebook |

Announce the path name and sequence to orient the user, then immediately invoke `find-source` with the source name as its argument. The path name is for user expectations only — it does NOT change `find-source`'s behaviour. Downstream toolkit `workflow.md` rules handle subsequent steps.

## What NOT to do

- Do not re-explain downstream skills after handing off
- Do not run `dlt init` or create any files yourself
- Do not ask more than one question before routing
- Do not re-invoke this skill after handing off to `find-source`
