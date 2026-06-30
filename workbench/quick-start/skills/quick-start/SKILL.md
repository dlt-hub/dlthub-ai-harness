---
name: quick-start
description: "Use when the user wants a guided end-to-end run from data to dashboard in a few prompts: 'show me a demo', 'give me a quick start', 'take me through the full workflow', 'how do I go from data to dashboard', 'walk me through ingestion to visualization', 'I want to try everything end-to-end'.
  Do NOT use when the user is asking what's available or where to start in general — use the `dlthub-router` skill (in init) for capability-discovery questions ('what can you do', 'what toolkits are there', 'I'm new to dlthub').
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
  - **Preferred — run `uvx dlthub-init@latest` yourself.** It is non-interactive and AI-aware, so an agent can run it directly — **this is also how you set up a clean new dlthub project** (`uvx dlthub-init@latest <dir>` scaffolds into a new directory). It scaffolds a dlthub workspace with AI support, collision-safe, in one step.
  - **Fallback (if `dlthub-init` is unavailable or errors)** — run `uvx --from "dlt[hub]" dlthub init` (equivalent to `uv init` + `uv add "dlt[hub]"` + `uv run dlthub init`), then `uv run dlthub ai init` to set up AI support.

  Wait for completion, then re-check status before continuing to Step 2.

  **Onboarding exception — only when the user asks to be onboarded or to be taught how to use dltHub** (e.g. "onboard me", "I want to learn dltHub"): ask the user to run `uvx dlthub-start@latest`. This scaffolds a fresh **playground** workspace — an onboarding experience, **not** where production workflows should live, and not for setting up an existing project. **NEVER run it yourself** — it is interactive and does not work when an agent runs it:

  ```
  uvx dlthub-start@latest
  ```

  It must be run by a human because it requires interaction for authentication; it only works in a real terminal — **do NOT use `!` mode for it**. Tell the user to run it in their own terminal. (For agent-driven setup of a clean new project, use `uvx dlthub-init@latest` above instead.)

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

## Routing default

**Production is the default path** when the user does not explicitly pick a depth. Any other path (Discover, Inspect, Full CDM) requires the user to opt in by name. This protects users from deploying pipelines that still carry debug-only settings (`dev_mode=True`, `single_page` paginators, tiny `per_page`, no incremental).

## Active path overrides in-skill "Next steps"

When `quick-start` announces a path (Production / Inspect / Full CDM / Discover), the sequence in that path's row is **authoritative** until the last step runs. When a skill called inside an active path returns, pick the next skill from the path table — **ignore** the skill's own "Next steps" section. The path completes after the last skill in its sequence runs, or when the user explicitly aborts.


## Handover to other toolkits

This toolkit is a router — after `quick-start` runs, the user is in one of the receiving toolkits.

### Outgoing (from quick-start)

All outgoing handoffs originate from `quick-start` after path confirmation:

- **workspace bootstrap** — when `dlthub ai status` reports missing prerequisites (no workspace, MCP not connected, missing dependencies), set it up yourself: preferred is to run `uvx dlthub-init@latest` (non-interactive, AI-aware, collision-safe — scaffolds a dlthub workspace with AI support in one step; this is also how you set up a clean new dlthub project — `uvx dlthub-init@latest <dir>` scaffolds into a new directory). Fallback if it's unavailable or errors: run `uvx --from "dlt[hub]" dlthub init` (equivalent to `uv init` + `uv add "dlt[hub]"` + `uv run dlthub init`), then `uv run dlthub ai init`. Re-check `dlthub ai status` once done. **Onboarding exception:** only when the user explicitly asks to be onboarded or taught how to use dltHub, ask them to run `uvx dlthub-start@latest` (a playground scaffold, not for production and not for an existing project). NEVER run it yourself, and do NOT use `!` mode for it — it must be run by a human because it requires interaction for authentication and only works in the user's own terminal.
- **rest-api-pipeline** → `find-source` — default for all four paths; source name is passed as the first argument. Every non-Discover path then runs `adjust-endpoint` after `debug-pipeline` to strip debug artifacts (dev_mode, single_page paginators, tiny per_page, missing incremental) before downstream validation, deploy, or exploration.
- **data-exploration** → `explore-data` — shortcut path when the user already has a loaded pipeline and wants to explore or visualize; no source name is passed
- **transformations** → `annotate-sources` — shortcut path when the user already has a loaded pipeline and wants to model or transform; no source name is passed
- **dlthub-platform** → `setup-runtime` — runs as part of the default Production path after `validate-data`; also reachable as a shortcut when the user already has a working pipeline and wants to deploy
