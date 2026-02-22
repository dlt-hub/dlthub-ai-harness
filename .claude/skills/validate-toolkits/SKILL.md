---
name: validate-toolkits
description: Validate toolkit components — check that external doc URLs are live and relevant, cross-references between skills/commands/rules resolve correctly, and fix what can be fixed. Use when the user asks to validate, review, or check toolkit quality.
argument-hint: <toolkit-path>
---

# Validate toolkit components

Deep-validate a toolkit's markdown files: external references, cross-references, and component accuracy.

Parse `$ARGUMENTS`:
- `toolkit-path` (optional): path to toolkit directory (e.g. `workbench/rest-api-pipeline`). If omitted, validate all toolkits under `workbench/`.

## 1. Build component map

Run the extraction tool to get the component map and file inventory:

```
uv run python tools/extract_refs.py [toolkit-path]
```

This outputs JSON with:
- **components**: lists of skills, commands, rules in the toolkit (for cross-reference resolution)
- **files**: each .md file with its URLs and surrounding context lines

Save the components map. You will process files **one at a time** in the next steps.

## 2. Process each file

For each file in the extraction output, do the following **before moving to the next file**:

### a. Validate URLs

For each URL in the file (use the context lines from the extraction):

1. **Fetch it** using WebFetch. Check if the page loads.
2. **Validate relevance** using the context: does the page content match what the surrounding text claims? For example, if context says "Essential Reading on resource config" and the URL points to a page about pipelines — that's a mismatch.
3. If a URL is dead (404) or redirects to unrelated content, mark as ERROR.
4. If a URL loads but content doesn't match the context, mark as WARNING.
5. Use web search to find the correct URL if a reference is broken but the intent is clear from context.

### b. Validate cross-references

Read the file and look for references to other components **in the same toolkit**. References are NOT limited to backtick formatting — look for natural language patterns like:
- "use the **debug-pipeline** skill"
- "see `validate-data`"
- "continue with create-pipeline"
- "check rules in workflow.md"
- "step 6b in create-pipeline"

For each cross-reference found:

1. **Resolve** against the component map. Does the referenced skill/command/rule exist?
2. If it resolves, **check context**: does the reference make sense? (e.g., "use debug-pipeline after a failed run" — does debug-pipeline actually handle post-failure inspection?)
3. If it doesn't resolve, try fuzzy matching:
   - Partial name match (e.g., "debug" could mean "debug-pipeline")
   - Similar names (e.g., "explore-data" might be the old name for "view-data")
4. If a match is found, **fix the reference** in the source file.
5. If no match can be found, mark as ERROR.

### c. Fix the file

Apply any fixes (broken URLs, renamed references) immediately before moving to the next file.

## 3. Report

After all files are processed, output a summary:

```
Validated: <toolkit-name>
Files scanned: N
URLs checked: N (M broken)
Cross-references checked: N (M broken)

FIXED:
  <file>: <old-ref> → <new-ref>

ERRORS:
  <file>: <description of unresolvable reference>

WARNINGS:
  <file>: <description of questionable content>
```

Errors must be resolved by the user.
