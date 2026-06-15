---
name: quick-start
description: "Use when the user wants a guided end-to-end run from data to dashboard in a few prompts: 'show me a demo', 'give me a quick start', 'take me through the full workflow', 'how do I go from data to dashboard', 'walk me through ingestion to visualization', 'I want to try everything end-to-end'.
  Do NOT use when the user is asking what's available or where to start in general — use the `toolkit-dispatch` skill (in init) for capability-discovery questions ('what can you do', 'what toolkits are there', 'I'm new to dlthub').
  Do NOT use when the user already has a specific task underway (debugging, adding an endpoint, deploying)."
argument-hint: "[data-source] [path]"
---

# Quick Start

Guide the user from zero to a deployed, production-ready pipeline in a few prompts. Make sure you keep the sampling for the first deployment. 

Parse `$ARGUMENTS`:
- `data-source` (optional): what the user wants to extract data from
- `path` (optional): one of `production` (default), `discover`, `inspect`, `cdm`

## Step 1 — Check workspace status

Run `uv run dlthub ai status`.

- If everything is set up: continue to Step 2.
- If prerequisites are missing (no workspace, MCP not connected, missing dependencies): briefly tell the user what is missing in one line, then set it up **in place**.
  - **Preferred — run `uvx dlthub-init@latest` yourself.** It is non-interactive and AI-aware, scaffolds an AI-supported project in place with per-file collision handling (merges `pyproject.toml`, never overwrites `secrets.toml`, unions `.gitignore`), pins `dlt[hub]`, and runs `uv sync` — `dlthub init` + `dlthub ai init` in one safe step.
  - **Fallback (if `dlthub-init` is unavailable or errors)** — drive the `bootstrap` / `/bootstrap:init-workspace` flow yourself: ensure `uv` + venv, then `uv add "dlt[hub]"` (installs `dlt[hub]`, not plain `dlt`), `uv run dlthub init`, `uv run dlthub ai init`.

  Wait for completion, then re-check status before continuing to Step 2.

  **Onboarding exception — only when the user asks to be onboarded or to be taught how to use dltHub** (e.g. "onboard me", "I want to learn dltHub"): ask the user to run `uvx dlthub-start@latest`. This scaffolds a fresh **playground** workspace — an onboarding experience, **not** where production workflows should live, and not for setting up an existing project. **NEVER run it yourself** — it is interactive and does not work when an agent runs it:

  ```
  uvx dlthub-start@latest
  ```

  It is interactive and only works in a real terminal — **do NOT use `!` mode for it**. Tell the user to run it in their own terminal.

## Step 2 — Present capability index and ask one question

If `$ARGUMENTS` already has both source and path, skip to Step 3.

If the user has mentioned an existing pipeline (has data already loaded), route directly:
- wants to explore or visualize → invoke `explore-data`
- wants to model or transform → invoke `annotate-sources`
- wants to deploy → invoke `setup-runtime`

Otherwise, show the capability table and depth menu, then ask: **"What do you want to extract data from?"**

```
INGEST     → REST API pipelines (find-source → create → debug → harden → validate)
EXPLORE    → Marimo dashboards (explore-data → build-notebook)
TRANSFORM  → Canonical data model — Kimball (annotate-sources → generate-cdm → create-transformation)
DEPLOY     → dltHub Runtime on a schedule (setup-runtime → prepare-deployment → deploy-workspace)

Pick a depth (default is Production):
  [1] Production  — ingest + harden + validate + deploy + visualize  ← default
  [2] Full CDM    — ingest + harden + validate + model + transform + deploy + visualize (~8 steps)
  [3] Inspect     — ingest + harden + validate + visualize (no deploy)
  [4] Discover    — ingest (demo only, leaves dev artifacts; explicit opt-in)

What do you want to extract data from?
```

**Default routing rule**: if the user answers with just a source name, or names a source without picking a depth, route to **Production**. Pick another path **only** if the user explicitly names it (e.g. "just a quick demo", "discover path", "skip deploy", "I just want to see the data", "no need to deploy", "Full CDM").

## Step 3 — Confirm path and hand off

Announce the step sequence for the chosen path, then invoke `find-source` with the source name.

| Path | Sequence |
|---|---|
| **Production** (default) | find-source → create-rest-api-pipeline → debug-pipeline → **adjust-endpoint** → validate-data → setup-runtime → prepare-deployment → deploy-workspace → explore-data → build-notebook |
| Full CDM | find-source → create-rest-api-pipeline → debug-pipeline → **adjust-endpoint** → validate-data → annotate-sources → create-ontology → generate-cdm → create-transformation → setup-runtime → prepare-deployment → deploy-workspace → explore-data → build-notebook |
| Inspect | find-source → create-rest-api-pipeline → debug-pipeline → **adjust-endpoint** → validate-data → explore-data → build-notebook |
| Discover (demo only) | find-source → create-rest-api-pipeline → debug-pipeline → explore-data → build-notebook |

**Why every non-Discover path includes `adjust-endpoint`**: `create-rest-api-pipeline` intentionally leaves debug artifacts behind for fast iteration — `dev_mode=True`, `single_page` paginators, low `per_page`, no incremental. `adjust-endpoint` removes those before validation/deploy/exploration. Skipping it leads to deploying a sample loader, not a real pipeline.

Announce the path name and sequence to orient the user, then immediately invoke `find-source` with the source name as its argument. The path name is for user expectations only — it does NOT change `find-source`'s behaviour. Downstream toolkit `workflow.md` rules handle subsequent steps.

**Production path hardening checklist** (delegated to `adjust-endpoint`, but state explicitly when announcing the path so the user knows the toy run will get hardened):
- Remove `dev_mode=True` from the pipeline
- Replace `single_page` paginators with the API-appropriate paginator (e.g. `header_link` for GitHub, `json_link` / `offset` / `page_number` elsewhere)
- Restore `per_page` to a normal value (typically 100)
- Add `incremental` cursors on resources that support it
- Remove any `.add_limit(N)` calls left from the first run

## What NOT to do

- Do not re-explain downstream skills after handing off
- Do not run `dlthub pipeline init` or create any files yourself
- Do not ask more than one question before routing
- Do not re-invoke this skill after handing off to `find-source`
