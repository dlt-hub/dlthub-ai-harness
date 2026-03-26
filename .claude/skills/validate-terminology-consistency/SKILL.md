---
name: validate-terminology-consistency
description: "Run the glossary linter across all toolkits to detect terminology inconsistencies, then interactively walk through each violation with the user to fix or skip it. Use when the user wants to fix terminology issues, correct glossary violations, or clean up vocabulary across the workbench."
---

# Validate Terminology Consistency

Run the glossary linter, then interactively fix each violation with user approval.

## Step 1: Run the linter

Run the glossary lint with LLM review:

```bash
make glossary-lint-review-cli 2>&1
```

This runs `tools/glossary_lint.py --review --cli workbench/` which:
1. Scans all markdown files across all toolkits using NLP (spaCy + sentence-transformers)
2. Finds candidate terminology violations against `terminology/glossary.yaml`
3. Sends candidates to Claude CLI for context-aware review
4. Returns a list of VIOLATIONS (confirmed issues) and ACCEPTABLE (false positives dismissed)

## Step 2: Parse the output

From the linter output, extract each VIOLATION. Each violation has:
- **File** — path and line number (e.g., `workbench/rest-api-pipeline/rules/workflow.md:1`)
- **Found** — the deprecated/incorrect term that was found
- **Preferred** — what it should be replaced with
- **Context** — the sentence where the term was found
- **Reason** — why this is a violation
- **Suggestion** — the corrected text

If there are **zero violations**, report "All clean — no terminology inconsistencies found." and stop.

## Step 3: Display all violations

First, show the user a complete table of ALL violations found:

```markdown
## Violations Found (N)

| # | File | Line | Found | Should be | Suggested fix |
|---|------|------|-------|-----------|---------------|
| 1 | path/to/file.md | 42 | "old term" | "new term" | "full corrected sentence" |
| 2 | ... | ... | ... | ... | ... |
```

This gives the user the full picture before any changes are made.

## Step 4: Walk through each violation

After showing the table, go through each violation one at a time:

1. **Read the actual file** at the reported line to get the exact current text (the linter works on cleaned/stripped markdown, so the actual file content may differ slightly).

2. **Ask the user** whether to apply the fix using AskUserQuestion:
   - Option 1: "Yes, fix it" — apply the suggested change
   - Option 2: "No, skip" — move to the next violation

3. **If the user says yes**: use the Edit tool to make the change in the file. Confirm the edit was made.

4. **If the user says no**: move on.

## Step 5: Summary report

After processing all violations, print a summary:

```
## Terminology Consistency Report

### Fixed (N)
| # | File | Line | Changed | To |
|---|------|------|---------|----|
| 1 | path/to/file.md | 42 | "old term" | "new term" |

### Skipped (N)
| # | File | Line | Found | Preferred | Reason skipped |
|---|------|------|-------|-----------|----|
| 1 | path/to/file.md | 10 | "old term" | "new term" | User declined |

### Summary
- Total violations found: X
- Fixed: Y
- Skipped: Z
```
