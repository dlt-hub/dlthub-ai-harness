---
name: review-pr
description: "Use when the user asks to review a pull request of the dltHub AI harness (this repo), by PR number or URL. Finds the toolkits the PR touches, runs the mechanical checks and validate-toolkits on those toolkits only, flags temporary changes that must not merge, missing version bumps and the eval sets the PR affects, and writes the review."
argument-hint: "<pr-url-or-number> [-- <optional instructions>]"
metadata:
  internal: true
---

# Review a pull request

Parse `$ARGUMENTS`:
- Everything before the first `--` (or all of it) is the **PR identifier** (URL or number), `PR_ID` below.
- Everything after the first `--` is **reviewer instructions**: extra focus areas. If absent, there are none.

Gather data in parallel where possible. A review reports: it never commits, pushes or comments on the PR unless the
user asks.

## 1. Check out the PR in a worktree

```sh
gh pr view PR_ID --json number,title,body,author,state,baseRefName,headRefName,url,comments,reviews,labels
git fetch origin pull/<number>/head:review-pr-<number>
git worktree add ../dlthub-ai-workbench-review-<number> review-pr-<number>
```

Work in that worktree (`WORKTREE` below) with absolute paths, and run `uv sync --all-groups` there. Remove it when the
review is done (`git worktree remove`), unless the user wants to keep it.

## 2. Find what the PR touches

```sh
gh pr diff PR_ID --name-only
gh pr diff PR_ID
```

- **Touched toolkits**: every `workbench/<toolkit>/` in the file list.
- **Renamed or removed components**: skill, rule or agent folders that the diff deletes or renames. Grep the whole
  repo (all toolkits, `evals/`, `tools/`, root docs) for their old names, and add every toolkit that still references
  one to the touched toolkits.
- **Repo files**: changes to `CLAUDE.md`, `TOOLKITS.md`, `EVALS.md`, `README.md`, `tools/`, `tests/`, `evals/`,
  `.claude-plugin/marketplace.json`.

## 3. Run the mechanical checks

```sh
make lint                                              # validator, tests, ruff, mypy, installs for every agent
python3 .github/scripts/version_check.py origin/<baseRefName>   # a changed toolkit bumps plugin.json and marketplace.json
gh pr checks PR_ID
```

Report each failure. A failing check is a required fix.

## 4. Validate the touched toolkits

Run the (`validate-toolkits`) skill on the touched toolkits only, for example
`/validate-toolkits workbench/local-workspace workbench/dlthub-platform`. Tell it that this is a review: it reports its
fixes as proposals and edits nothing. Collect its ERRORS, RULES and WARNINGS.

## 5. Find temporary changes that must not merge

Search the added lines of the diff for:
- lines marked `TEMPORARY`, `remove before merge`, `WIP`, `FIXME`, `XXX`, or `TODO` with no issue link;
- preview or branch docs and services (`*.workers.dev`, `*-docs.*`, `localhost`, `127.0.0.1`) in place of
  `https://dlthub.com/docs/`;
- dependencies taken from a git URL, an archive, a local path or a branch (`[tool.uv.sources]`, `archive/`, `.zip`),
  pre-releases (`a0`, `b1`, `rc`) where a release exists, and commented-out alternatives;
- toolkit sources or install commands pointing at a branch or a fork;
- disabled tests or eval queries (`skip`, `disabled: true`) without a reason.

Each one blocks the merge unless the PR body says it stays, and why.

## 6. Name the evals the PR affects

For each skill description that the diff changes, list the eval sets under `evals/<toolkit>/<skill>/` that cover it
or the skills that compete with it in the same install set (the router, the sibling skills). Do not run evals: they
are costly. Recommend which ones to run, and let the user decide.

## 7. Write the review

- **Summary**: what the PR does and why.
- **Touched toolkits**: the list, with the toolkits added because they reference a renamed component.
- **Checks**: `make lint`, the version check and CI, with each failure.
- **Validation**: the ERRORS, RULES and WARNINGS of `validate-toolkits`, grouped by toolkit.
- **Temporary changes**: each one with its file and line, marked as a blocker.
- **Evals to run**: the eval sets from step 6.
- **Reviewer instructions**: a section for each point, only when instructions were given.
- **Verdict**: merge, merge after fixes (list them), or not yet.
