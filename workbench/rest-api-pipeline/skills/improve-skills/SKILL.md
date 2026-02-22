---
name: improve-skills
description: Improve existing skills based on the current session. Use at the end of a session (or when the user asks) to capture new debugging patterns, data validation tricks, querying techniques, doc references, or workflow improvements learned during the session. Keeps skills lean and personalized.
---

# Improve skills from session

Review the current session and update skills with essential learnings. Skills are the team's institutional memory — keep them lean, specific, and actionable.

## Principles

- **Read the skill first** — always read the current SKILL.md before proposing changes. Don't duplicate what's already there.
- **Lean updates only** — add the minimum needed. A single bullet point or a 3-line code snippet is often enough.
- **Real problems only** — only add things that actually happened in this session or that the user explicitly asked to capture. No hypothetical scenarios.
- **Doc references matter** — if you found a docs page that was essential to solving a problem, add it as an "Essential Reading" link.
- **Tools and commands** — if a specific CLI command or MCP tool was key to diagnosing an issue, add it.
- **Don't restructure** — don't reorganize or rewrite existing skill content. Append to the right section or add a new subsection.

## Process

### 1. Scan the session for learnings

Review the conversation looking for:

**Debugging patterns** (`debug-pipeline`):
- New error types and their root causes
- Diagnostic commands that were useful
- Config settings that helped (e.g., verbosity, timeouts)
- Workarounds for specific API behaviors

**Data validation** (`validate-data`):
- New data type issues (e.g., money as float → Decimal)
- Schema surprises (unexpected nesting, missing columns)
- processing_steps patterns that worked

**Data access** (`view-data`):
- ibis gotchas (e.g., `.distinct()` is table-level, deferred refs in mutate)
- New ReadableRelation or dataset API usage

**Pipeline creation** (`create-rest-api-pipeline`, `new-endpoint`):
- API-specific auth or pagination quirks
- Config resolution surprises
- Source/resource parameterization patterns

**Workflow** (`workflow.md`):
- Missing cross-references between skills
- New skills that should be in the workflow
- Steps that are in the wrong order

### 2. Read the target skills

For each learning, read the relevant SKILL.md. Check:
- Is this already covered?
- Where does it fit best? (which section)
- Would it contradict or duplicate existing content?

### 3. Propose changes to the user

Present a summary of proposed updates:

```
Proposed skill updates:

debug-pipeline:
  + [section] Added: <brief description>

validate-data:
  (no changes)

query-data:
  + [section] Added: <brief description>
```

Get user approval before editing. The user may want to adjust, skip, or add more.

### 4. Apply changes

Edit the SKILL.md files. For each change:
- Add to the most relevant existing section
- If no section fits, add a new subsection at the end (before "Next steps" if present)
- Include doc links as `**Ref:** <url>` or `**Essential Reading:** <url>`
- Keep code examples minimal — 3-5 lines max

### 5. Update workflow if needed

Check if `workflow.md` cross-references are still accurate after skill changes. Update if new skills were added or handoff points changed.
