# Quick Start workflow

## Workflow Entry
**ALWAYS** start with **Quick start** (`quick-start`) SKILL — present the capability index, ask what the user wants to extract, pick a depth, and route to `find-source`

## Core workflow
1. **Quick start** (`quick-start`) — check workspace status, show capability table and depth menu, confirm path, hand off to `find-source` with source name

## Handover to other toolkits

This toolkit is a router — after `quick-start` runs, the user is in one of the receiving toolkits.

### Outgoing (from quick-start)

All outgoing handoffs originate from `quick-start` after path confirmation:

- **bootstrap** → `/init-workspace` — when `dlt ai status` reports missing prerequisites (no workspace, MCP not connected, missing dependencies); user must confirm before install
- **rest-api-pipeline** → `find-source` — default for all four paths; source name is passed as the first argument
- **data-exploration** → `explore-data` — shortcut path when the user already has a loaded pipeline and wants to explore or visualize; no source name is passed
- **transformations** → `annotate-sources` — shortcut path when the user already has a loaded pipeline and wants to model or transform; no source name is passed
- **dlthub-runtime** → `setup-runtime` — shortcut path when the user already has a working pipeline and wants to deploy; no source name is passed
