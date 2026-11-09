# Anthropic plugin directory (claude.ai/directory)

Submit through the developer portal at https://claude.ai/directory/manage, "Submit new", "Plugin bundle". Needs a paid claude.ai plan and a GitHub connection with push access. One plugin folder per submission. Checklist source: https://claude.com/docs/plugins/pre-submission-checklist (read 2026-10-30). Run `claude plugin validate ./workbench/<toolkit>` first, then the portal's **Validate**.

NOTHING is submitted. The portal's Validate was not run (needs login), so the results below are our own reading of the checklist.

## Checklist against this repo

| Check | Result if missed | Status | Fix needed |
|---|---|---|---|
| Plugin folder contains `.claude-plugin/plugin.json` | Blocks | PASS (all 13 toolkits) | none |
| One plugin per submission | Blocks | PASS (process) | submit each `workbench/<name>` separately |
| Everything a plugin uses is inside its folder | Blocks | UNVERIFIED | Toolkits depend on `init` (rules, secrets) via `toolkit.json`, which Claude's marketplace does not read. Installed alone, a toolkit lacks the `init` rules. Decide: copy or document. |
| No symlinks, submodules, LFS, `.DS_Store`, `.gitattributes` filters | Blocks | PASS (none found under `workbench/`, no `.gitattributes`) | none |
| Repo < 50 MiB archived, < 10,000 files, each file < 5 MiB | Validation stops | PASS (no file > 256 KiB, max 18 files per toolkit) | none |
| Name: lowercase, digits, hyphens, <= 64 chars | Warning | PASS | none |
| Name not reserved/generic, unique across orgs | Blocks or held | FAIL (risk): generic names `init`, `bootstrap`, `performance`, `transformations`, `quick-start`, `one-shot`. Uniqueness vs other orgs could not be checked (portal only). | Prefer a `dlthub-` prefix like `dlthub-platform`. Name must match directory and `marketplace.json` (validator rule), so a rename moves the directory. Keep `rest-api-pipeline`, `sql-database-pipeline`, `data-quality`, `data-exploration`, `filesystem-pipeline` unless Validate says "Name is taken". |
| `description`, `author`, `version` set | Warning | PASS (all 13) | none |
| README >= 40 words (code blocks excluded) in the plugin folder | Blocks | FAIL: 12 of 13 toolkits have no README; `workbench/init/README.md` is 21 words | Write `workbench/<name>/README.md` (>= 40 words of prose) per submitted toolkit. Disclose everything the plugin runs, sends and fetches (security scan reads it): runs `uv run dlthub ...`, reads local project files, talks to the dltHub platform. |
| LICENSE file in folder or `license` in plugin.json | Blocks | PASS via the `license` URL in all plugin.json (the value dlt's `test_dependency_map_workbench` pins) | Optional: copy `LICENSE` into each folder. Whether a proprietary license passes the Software Directory Policy is UNVERIFIED (policy not read). |
| Local MCP: `uv run` needs `--locked`/`--frozen`; `uvx pkg==x` pinned | Blocks ("Unpinned uvx launcher") | FAIL in `init` (`.mcp.json`) and `plugin.json` of `rest-api-pipeline`, `sql-database-pipeline`, `transformations`, `dlthub-init-skills`: `uv run dlthub ai mcp --stdio` | A: add `--locked` (needs a `uv.lock` in the user's project, which a plugin cannot provide; likely breaks). B: `uvx --from "dlt[hub]==<ver>" dlthub ai mcp --stdio`: pinned, but always "held for a reviewer" and ignores the user's project venv. C: ship public plugins without the MCP entry. Needs a decision; not changed. |
| MCP command not via shell / `-c` | Held | PASS | none |
| `hooks/hooks.json` valid | Blocks | PASS (no hooks directories) | none |
| Non-image files < 256 KiB, <= 512 files, text/images/fonts only | Held | PASS | none |
| Skill/command front matter valid | Blocks | PASS (enforced by `make validate-toolkits`) | none |
| No credentials in files | Blocks | UNVERIFIED (no scan run) | grep before submit |
| `claude plugin validate` clean | n/a | NOT RUN | run per toolkit |
| Post-submit security scan | Reject/hold | UNVERIFIED | README disclosure above |

Net blockers: README missing/short (all), unpinned `uv run` MCP launcher (5 toolkits). Likely holds: generic names.

## Form answers per public toolkit

Common: Repository `https://github.com/dlt-hub/dlthub-ai-harness`. Branch/tag: release tag (e.g. `v0.1.1`) or `master`. Category: `data` (matches marketplace.json; the portal's category list was not seen, check it). Author: ScaleVector GmbH. License: dltHub License (`https://github.com/dlt-hub/dlthub-ai-harness/blob/master/LICENSE`).

Which toolkits are "public" is a dltHub decision. Suggested: the six below. `init` is the shared foundation and holds the MCP, `bootstrap` is unlisted, `one-shot` and `dlthub-init-skills` are demo flows.

| Plugin name | Path | Description |
|---|---|---|
| rest-api-pipeline | workbench/rest-api-pipeline | Build dlt pipelines for REST APIs: find a source, scaffold the pipeline, add endpoints and incremental loading, debug it, validate the data and view it in a report. Requires dlt[hub]. |
| sql-database-pipeline | workbench/sql-database-pipeline | Load tables from any SQLAlchemy-supported database into a destination with dlt, and tune performance with the available backends. Requires dlt[hub]. |
| filesystem-pipeline | workbench/filesystem-pipeline | Load CSV, Parquet, JSONL or custom files from local disk, S3, GCS, Azure or SFTP into a destination with dlt. Requires dlt[hub]. |
| data-exploration | workbench/data-exploration | Get quick insights from a dlt pipeline: profile its tables, plan charts and assemble a marimo dashboard. Requires dlt[hub]. |
| data-quality | workbench/data-quality | Add column-level checks and load metrics to dlt pipelines, run them on every load and review failures with diagnosis. Requires dlt[hub]. |
| transformations | workbench/transformations | Turn raw dlt pipeline data into a Canonical Data Model: annotate sources, build an ontology, design a Kimball-style model and write @dlt.hub.transformation functions. Requires dlt[hub]. (rename candidate: dlthub-transformations) |

Others: `dlthub-platform` (v0.3.0), `performance` (v0.2.0, rename candidate `dlthub-performance`), `quick-start`, `init`, `one-shot`, `dlthub-init-skills`, `bootstrap`; descriptions in `.claude-plugin/marketplace.json`.

## Platform caveats

Hooks and local MCP servers are ignored on claude.ai chat; they load in Cowork and Claude Code. Raise `version` in `plugin.json` and `marketplace.json` every release. The official `claude-plugins-official` repo is a different route (partner form https://clau.de/plugin-directory-submission), not covered here.
