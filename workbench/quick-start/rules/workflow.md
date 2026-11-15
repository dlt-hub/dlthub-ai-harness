# Quick Start workflow

## Workflow Entry
**ALWAYS** start with **Quick start** (`quick-start`) SKILL — present the capability index, ask what the user wants to extract, pick a depth, and route to `find-source`

## Core workflow
1. **Quick start** (`quick-start`) — check workspace status, show capability table and depth menu (Production default), confirm path, hand off to `find-source` with source name

## Handover to other toolkits

### Outgoing (from quick-start)

- **The active path** carries into every toolkit it runs. When `quick-start` announced a path (Production / Inspect / Full CDM / Discover), the sequence in that path's row wins until its last step runs or the user aborts: when a skill called inside the path returns, pick the next skill from the path table, NOT from the skill's own "Next steps" section.
