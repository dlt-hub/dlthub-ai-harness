# Quick Start workflow

## Workflow Entry
**ALWAYS** start with **Quick start** (`quick-start`) SKILL — present the capability index, ask what the user wants to extract, pick a depth, and route to `find-source`

## Routing default

**Production is the default path** when the user does not explicitly pick a depth. Any other path (Discover, Inspect, Full CDM) requires the user to opt in by name. This protects users from deploying pipelines that still carry debug-only settings (`dev_mode=True`, `single_page` paginators, tiny `per_page`, no incremental).

## Active path overrides in-skill "Next steps"

When `quick-start` announces a path (Production / Inspect / Full CDM / Discover), the sequence in that path's row is **authoritative** until the last step runs. When a skill called inside an active path returns, pick the next skill from the path table — **ignore** the skill's own "Next steps" section. The path completes after the last skill in its sequence runs, or when the user explicitly aborts.

## Core workflow
1. **Quick start** (`quick-start`) — check workspace status, show capability table and depth menu (Production default), confirm path, hand off to `find-source` with source name

## Handover to other toolkits

This toolkit is a router — after `quick-start` runs, the user is in one of the receiving toolkits.

### Outgoing (from quick-start)

All outgoing handoffs originate from `quick-start` after path confirmation:

- **workspace bootstrap** — when `dlthub ai status` reports missing prerequisites (no workspace, MCP not connected, missing dependencies), set it up **in place**: preferred is to run `uvx dlthub-init@latest` yourself (non-interactive, AI-aware, collision-safe — `dlthub init` + `dlthub ai init` in one step). Fallback if it's unavailable or errors: drive the `bootstrap` / `/bootstrap:init-workspace` flow — `uv add "dlt[hub]"` (installs `dlt[hub]`, not plain `dlt`), `uv run dlthub init`, `uv run dlthub ai init`. Re-check `dlthub ai status` once done. **Onboarding exception:** only when the user explicitly asks to be onboarded or taught how to use dltHub, ask them to run `uvx dlthub-start@latest` (a playground scaffold, not for production and not for an existing project). NEVER run it yourself, and do NOT use `!` mode for it — it is interactive and only works in the user's own terminal.
- **rest-api-pipeline** → `find-source` — default for all four paths; source name is passed as the first argument. Every non-Discover path then runs `adjust-endpoint` after `debug-pipeline` to strip debug artifacts (dev_mode, single_page paginators, tiny per_page, missing incremental) before downstream validation, deploy, or exploration.
- **data-exploration** → `explore-data` — shortcut path when the user already has a loaded pipeline and wants to explore or visualize; no source name is passed
- **transformations** → `annotate-sources` — shortcut path when the user already has a loaded pipeline and wants to model or transform; no source name is passed
- **dlthub-platform** → `setup-runtime` — runs as part of the default Production path after `validate-data`; also reachable as a shortcut when the user already has a working pipeline and wants to deploy
