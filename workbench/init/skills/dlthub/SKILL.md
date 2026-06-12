---
name: dlthub
description: "The entry point for building anything with dlthub. Use this skill to discover dlthub's capabilities, pick the right workflow, and install the toolkit that fits the user's intent. MUST use when the user asks 'what can you do', 'what can I build', 'what are toolkits', 'what's available', 'how do I build a pipeline', 'how do I load data from <source>', 'I want to pull data from a REST API', 'ingest from a SQL database', 'load CSVs from S3', 'how do I make reports / dashboards', 'how do I transform / model my data', 'how do I add data quality checks', 'how do I deploy / schedule a pipeline', 'I'm new to dlthub', 'where do I start', or seems unsure what to do next after setup. Also use whenever the user expresses a data-engineering goal but no matching workflow toolkit is installed yet — this skill installs it on demand. Do NOT use when a specific task is already in progress (debugging a pipeline, validating data, adding endpoints) and its toolkit is installed. Do NOT use when the user explicitly wants a guided end-to-end demo — use **quick-start** for that."
---

# dlthub

Route the user to the right toolkit and skill.

## Step 1: Discover what's available

**Prefer MCP** — use the `list_toolkits` tool from `dlt-workspace-mcp` to get the current toolkit catalog.

**CLI fallback** (if MCP is not connected): `dlthub --non-interactive ai toolkit list`

Toolkits marked `(installed: <version>)` are ready to use. Others need installing first.

## Step 2: For installed toolkits, get skill details

Use `toolkit_info` MCP tool (or `dlthub --non-interactive ai toolkit info <name>` CLI) on each **installed** toolkit.
This returns skill names, descriptions (with "Use when..." patterns), and workflow rules — use these to match user intent.

## Step 3: Route by intent

Match the user's request to the best skill using descriptions from step 2. If no installed toolkit matches, suggest installing one.

**Install command:** `dlthub --non-interactive ai toolkit install <name>`

## Step 4. Confirm & enable mcp
```
uv run dlthub ai status
```
1. you should see new toolkit and its entry skill
2. if you see any **WARNING** related to mcp server (ie. cannot be started) - **fix the problem** using provided error message

## Step 5: Handover

1. If a new toolkit got installed ask user to restart the session
2. Do not start any workflows or skills on your own