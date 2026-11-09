# Cursor Marketplace

Submit at https://cursor.com/marketplace/publish with a link to a public Git repo. Terms: https://cursor.com/marketplace-publisher-terms (as summarized in our research, 2026-10-30; the terms page itself was not re-read for this file). NOT submitted.

## License blocker

Cursor requires plugins to be open source under a permissive license (MIT, BSD, Apache-2.0 are fine; GPL, AGPL, LGPL are not). This repo is under the proprietary **dltHub License** (`LICENSE`, "Copyright 2026 ScaleVector, GmbH. All rights reserved.", linked from the `license` field of every `plugin.json`). That is not open source and not permissive, so the submission would be rejected, and Cursor may reject without giving reasons. Listing is not possible until either:

1. the repo (or a separate public repo holding the Cursor-facing subset) is relicensed under MIT/BSD/Apache-2.0, or
2. dltHub decides not to list on Cursor.

This is a legal call for dltHub, not a technical one. The toolkits also only work with `dlt[hub]`, which is itself under the dltHub EULA; a permissive license on the toolkit text does not change that.

## Submission info (if the blocker is lifted)

- Repository: https://github.com/dlt-hub/dlthub-ai-harness (public)
- Manifest layout: whether Cursor accepts our multi-plugin `marketplace.json` with `source: ./workbench/<name>` was not confirmed. UNVERIFIED.
- Plugins: same names, descriptions and paths as the table in `anthropic-directory.md`.
- Publisher: ScaleVector GmbH; identity/business check required.
- Hooks, MCP, rules, skills, agents and commands are supported. No size limits stated.
- Publishers may not charge users for listed plugins.
- Updates: each update is reviewed; the publisher requests a re-index (terms 2.1). Already on the release checklist in CONTRIBUTING.md. A forum post says listings are pinned to a commit (unofficial).
- MCP: plugins start `uv run dlthub ai mcp --stdio`, which needs `uv` and the user's dlt project. The harness README already tells Cursor users to enable `dlt-workspace-mcp` manually in Cursor Settings > MCP.
