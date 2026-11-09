# Contributing

## Branches

- `master` is the release branch and the GitHub default. Users install from it.
- `devel` is where all work goes. Open feature PRs against `devel`.
- A PR to `master` must come from `devel` (release) or `hotfix/*` (hotfix). The `Version check` workflow enforces this.

## Versions

Claude Code updates a user's plugin only when `version` goes up. If a PR changes any file under `workbench/<toolkit>/`, bump the semver in both:

- `workbench/<toolkit>/.claude-plugin/plugin.json`
- the matching entry in `.claude-plugin/marketplace.json`

The `Version check` workflow fails the PR (naming the toolkit) if either is not higher than on the base branch. Check locally with `python3 .github/scripts/version_check.py origin/devel`.

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

## Release checklist

- [ ] Version check is green; every changed toolkit has a bumped version in `plugin.json` and `marketplace.json`
- [ ] Tag `vX.Y.Z` pushed
- [ ] GitHub release exists with notes
- [ ] Request a Cursor re-index
- [ ] Upload the OpenAI ZIP
- [ ] Announce the release
