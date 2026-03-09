---
name: toolkit-dispatch
description: "Helps users figure out what they can build with dlt and which workflow to start. MUST use this skill when the user asks questions like 'what can you do', 'how do I build a pipeline', 'how do I make reports', 'how do I deploy', 'what are toolkits', 'what's available', 'I'm new to dlt', 'where do I start', or seems confused about what to do next after initial setup. Also use when the user asks broad capability questions about data engineering with dlt. Do NOT use when the user has a specific task in progress like debugging a pipeline, validating data, or adding endpoints."
---

# Toolkit dispatch

Route the user to the right toolkit and skill.

## Step 1: Discover what's available

**Prefer MCP** — use the `list_toolkits` tool from `dlt-workspace-mcp` to get the current toolkit catalog.

**CLI fallback** (if MCP is not connected): `dlt --non-interactive ai toolkit list`

Toolkits marked `(installed: <version>)` are ready to use. Others need installing first.

## Step 2: For installed toolkits, get skill details

Use `toolkit_info` MCP tool (or `dlt --non-interactive ai toolkit <name> info` CLI) on each **installed** toolkit.
This returns skill names, descriptions (with "Use when..." patterns), and workflow rules — use these to match user intent.

## Step 3: Route by intent

Match the user's request to the best skill using descriptions from step 2. If no installed toolkit matches, suggest installing one.

**Install command:** `dlt --non-interactive ai toolkit <name> install`

## Step 4. Confirm & enable mcp
```
uv run dlt ai status
```
1. you should see new toolkit and its entry skill
2. if you see any **WARNING** related to mcp server (ie. cannot be started) - **fix the problem** using provided error message

## Step 5: Handover

1. If a new toolkit got installed ask user to restart the session
2. Do not start any workflows or skills on your own