# github/awesome-copilot (external plugin)

Public external plugins go through the issue form in github/awesome-copilot (do not edit `plugins/external.json`). Fields are from their CONTRIBUTING.md "External Plugin Submissions" (read 2026-10-30). NOT submitted. Placeholders in `<...>` must be filled after a release tag exists.

## Draft issue-form content (one issue per plugin)

| Field | Value |
|---|---|
| Plugin name | `rest-api-pipeline` (repeat per plugin) |
| Short description | Build dlt pipelines for REST APIs: find a source, scaffold the pipeline, add endpoints and incremental loading, debug it, validate the data and view it in a report. Requires dlt[hub]. |
| GitHub repository (`owner/repo`) | `dlt-hub/dlthub-ai-harness` |
| Plugin path inside the repository | `workbench/rest-api-pipeline` (must not point to `plugin.json`) |
| Ref to review (`ref`) | release tag, e.g. `v<X.Y.Z>`, not a branch |
| Commit SHA (`sha`) | `<40-char SHA of the tag commit>` (`git rev-parse v<X.Y.Z>^{commit}`) |
| Plugin version | semver, must equal `version` in the plugin manifest, e.g. `0.1.1` |
| License identifier | The LICENSE URL from plugin.json, or `LicenseRef-dltHub` if the form wants an SPDX-style id (not SPDX: gives a warning; proprietary is allowed but warned) |
| Author name | ScaleVector GmbH |
| Author URL (optional) | https://dlthub.com |
| Homepage URL (optional) | https://dlthub.com/docs |
| Keywords/tags | dlthub, etl, data-pipeline, python (from `marketplace.json`) |
| Notes for reviewers | Skills, rules and a local MCP server (`uv run dlthub ai mcp --stdio`); requires dlt[hub]. Proprietary license, see LICENSE. |
| Checkboxes | public repo; immutable ref/sha; repository policies; no duplicate listing |

Other plugin paths, names, descriptions and tags: `anthropic-directory.md` and `.claude-plugin/marketplace.json`.

## Gates and likely problems

1. Intake validation (fields present and well-formed).
2. Quality gates: manifest compliance, `vally lint` (Agent Skills spec, valid file references), Copilot CLI install smoke test, version equals source manifest, ref/SHA consistent.
3. Maintainer comments `/approve` or `/reject <reason>`.

- Manifest: they want a `plugin.json` with `name`, `description`, `version` (we have these in `.claude-plugin/plugin.json`). Whether the `.claude-plugin/` location is accepted, and the `extensions.com.github.awesome-copilot` key, are UNVERIFIED (CONTRIBUTING.md was read through a summarizer).
- Our `rules/` files are catch-all instructions; our research notes say instructions are not part of plugins, so rules may not install. UNVERIFIED.
- An in-repo MCP config is a higher-risk review tier.
- `vally lint` was not run (not available locally).
- Version bumps need a PR to `external.json`; 6-month re-review.
