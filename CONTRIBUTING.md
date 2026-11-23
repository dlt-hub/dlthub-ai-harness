# Contributing

This guide is for the dltHub team only. We do not accept outside contributions to the harness.

## Branches

- `master` is the release branch and the GitHub default. Users install from it.
- `devel` is where all work goes. Open feature PRs against `devel`.
- A PR to `master` must come from `devel` (release) or `hotfix/*` (hotfix). The `Version check` workflow enforces this.

## Versions

Claude Code updates a user's plugin only when `version` goes up. If a PR changes any file under `workbench/<toolkit>/`, bump the semver in both:

- `workbench/<toolkit>/.claude-plugin/plugin.json`
- the matching entry in `.claude-plugin/marketplace.json`

The two versions must be equal. The `Version check` workflow fails the PR (naming the toolkit) if they differ, or if either is not higher than on the base branch. Check locally with `python3 .github/scripts/version_check.py origin/devel`.

## Release flow

Releases are manual, by one owner.

1. Open a PR `devel` -> `master` and merge it. Versions were already bumped in the feature PRs; bump any that are missing.
2. Tag the merge commit on `master`: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. The `Release` workflow creates the GitHub release with auto-generated notes.
4. Run the checklist below.

## Hotfix flow

1. Branch `hotfix/<name>` from `master`, fix, bump the version of the affected toolkit.
2. PR to `master`, merge, then release as above (tag, checklist).
3. Merge `master` back into `devel` so the fix and version bump are not lost.

## After a release

Users get the latest commit on `master`, not the tag. The tag marks the release and holds the notes. Each channel picks up the new code differently:

| Channel | Reads from | How users get the update |
|---|---|---|
| Claude Code | `master` (default branch) | Auto-update is off for third-party marketplaces. Users run `/plugin marketplace update dlthub-ai-harness`, then `/plugin update <toolkit>`, or turn on auto-update in `/plugin` > **Marketplaces**. A toolkit updates only if its `version` changed. |
| `dlthub ai` CLI | `master` | Users run the install or update command again. |
| Cursor | the repo, after a re-index | We request a re-index (checklist). |
| OpenAI / Codex directory | the ZIP we upload | We upload a new ZIP, which OpenAI reviews again. |
| skills.sh | `master` (default branch) | Users run `npx skills add` again. |

So a merge to `master` is the release, and a toolkit without a version bump does not reach Claude Code users.

To stay on one release, a user can add the marketplace at its tag, for example:

```
/plugin marketplace add https://github.com/dlt-hub/dlthub-ai-harness.git#v0.2.0
```

## Release checklist

- [ ] Version check is green; every changed toolkit has a bumped version in `plugin.json` and `marketplace.json`
- [ ] Tag `vX.Y.Z` pushed
- [ ] GitHub release exists with notes
- [ ] Request a Cursor re-index
- [ ] Upload the OpenAI ZIP
- [ ] Announce the release

## Submit to directories

We submit only the launcher, `workbench/dlthub-setup`. It has a README, its own Apache-2.0 `LICENSE`, no hooks and no MCP. The toolkit plugins are deprecated and are not submitted.

**Anthropic directory.** [Submission guide](https://claude.com/docs/plugins/submit), [pre-submission checklist](https://claude.com/docs/plugins/pre-submission-checklist).

1. Run `claude plugin validate ./workbench/dlthub-setup`. It checks only the format, not the directory rules.
2. Open the [developer portal](https://claude.ai/directory/manage), select **Submit new**, then **Plugin bundle**. Your GitHub account must be connected on claude.ai.
3. Set the source: repository `dlt-hub/dlthub-ai-harness`, plugin path `workbench/dlthub-setup`, the release tag.
4. Run the portal's **Validate**, then fill in the listing, data handling and compliance steps.

Each plugin folder is one submission. Raise `version` on every release, or users keep the cached copy. In claude.ai chat, hooks and local MCP servers are ignored; they load in Cowork and Claude Code.

**OpenAI / Codex directory.** [Submission guide](https://developers.openai.com/plugins/deploy/submission). Run `make codex-zip` and upload `dist/dlthub-setup-codex.zip`. The build fails when the launcher breaks a directory rule. Every change to metadata or skills needs a new ZIP.

**Cursor Marketplace.** [Publisher terms](https://cursor.com/marketplace-publisher-terms). Submit the repository link at https://cursor.com/marketplace/publish.

- Plugins are free. A publisher must not charge users.
- Open-source parts must use a permissive license, such as MIT, BSD or Apache-2.0.
- Cursor reviews every update. After a change, we request a re-index (see the release checklist).
