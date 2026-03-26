---
name: generate-glossary
description: Generate the dlt controlled vocabulary and glossary markdown files from the dlt source code. Use when the user wants to update, rebuild, or regenerate the dlt glossary or vocabulary files.
---

# Generate dlt Glossary

Rebuild the dlt controlled vocabulary and glossary from source.

## Prerequisites

This skill must run from the **project root** (`/Users/tjean/projects/dlthub-ai-workbench` or wherever the repo is checked out). Verify with:

```bash
ls tools/generate_dlt_glossary.py
```

If the file is not found, ask the user to `cd` to the project root before continuing.

## Steps

### 1. Generate context files

Run the generator script to extract vocabulary and frequency data from the dlt source code:

```bash
python tools/generate_dlt_glossary.py
```

This writes context files under `.vocabulary/`:
- `.vocabulary/vocabulary.md` — raw term list
- `.vocabulary/frequency.txt` — term frequencies
- `.vocabulary/dlt-api.json` / `dlt-api-compressed.json` — API surface

Wait for the script to complete successfully before continuing.

### 2. Generate glossary markdown

Generate a natural language (plain English) glossary for the Python library `dlt` at `.vocabulary/glossary.md`. 

The glossary should:
- Highlight key constructs and their relationships
- Inform documentation writing for wording and semantic consistency across the product
- Be distilled (not exhaustive) — e.g., explain what normalization is rather than listing every normalizer implementation
- Use two input files:
  1. `.vocabulary/dlt-api-compressed.json` — a ~300k token JSON representation of the full Python API
  2. `.vocabulary/frequency.txt` — terms ordered by frequency (frequent = important/semantically consistent; infrequent = likely typos or inconsistent wording)
- Use `jq` to efficiently query the large JSON file rather than reading it all at once

Then write `.vocabulary/glossary.md` with the following structure.

### 3. Confirm output

Report the files written under `.vocabulary/` and ask the user to review `.vocabulary/glossary.md`.
