# Verified sources: copies, maintenance notes and updates

Verified sources: https://dlthub.com/docs/dlt-ecosystem/verified-sources.md
Source code and the latest notes: https://github.com/dlt-hub/verified-sources (folder `sources/<source>/`)

## Find the docs page

The docs page has the setup, credentials, resources and arguments of the source. Read it before you write or change the pipeline, and follow it like a skill.
1. `<source>/README.md` links it in its first lines. Add `.md` to the URL for the markdown version.
2. Without the link, try `https://dlthub.com/docs/dlt-ecosystem/verified-sources/<source>.md`. Most pages are named after the source folder.
3. If the URL returns 404, the page has another name: find the source in the index, https://dlthub.com/docs/dlt-ecosystem/verified-sources.md.
4. A few sources have no page. Use the README and the code.

## What `dlthub pipeline init` copies

`dlthub pipeline init <source> <destination>` copies a verified source into the project:
- its code, in the `<source>/` folder, with `README.md` and, for a versioned source, `version.py`
- an example script, `<source>_pipeline.py`
- a record in `.dlt/.sources`: `last_commit_sha` and `last_commit_timestamp` of the copy, a hash of each file, and `dlt_version_constraint`

The copy is the user's code. Upgrading dlt does not change it.

## The maintenance notes in `<source>/README.md`

They are written for developers and coding agents. Setup and usage are in the dlt docs page that the README links. The README answers two questions:
- **Can I upgrade safely from a previous version?** → **Changelog**, one entry per version, newest first.
  - The **Upgrade** line comes first. It says `safe`, or it lists the steps in order and what happens without them: failed runs, or missed, duplicated or mixed rows. It also says whether the incremental state carries over.
  - Bullets marked **breaking**, new, changed or fixed name the resource whose data changes. A breaking bullet says what fails.
- **What do I do when something goes wrong?** → **Maintenance & Troubleshooting** (**Operations** in older copies). It lists limits, quirks, failures and their workarounds, learned from running against the upstream: run times, throttling, paging quirks, state, limits. Each fact names its source: a run on the test account, a doc or a PR.

The other sections serve the source's own development: **Extension points** (where to add an endpoint, a field type or a transformer), **Seeding** and **Tests**.

A copy without `version.py` predates the first numbered version, usually 1.0.0. It may come from any commit (`.dlt/.sources` records which), so it cannot be upgraded in place. The Changelog entry of the first numbered version gives the steps to reload. For troubleshooting, read the latest notes upstream.

## Checks before you debug or change the source code

1. **Newer version**: compare the installed `__version__` with the Changelog at `https://raw.githubusercontent.com/dlt-hub/verified-sources/master/sources/<source>/README.md`. The entries above the installed version are fixes the copy does not have.
2. **dlt version**: the installed dlt (`uv run python -c "import dlt; print(dlt.__version__)"`) must satisfy `dlt_version_constraint` in `.dlt/.sources`. `uv run dlthub --non-interactive pipeline init --list-sources` marks a source that needs a newer dlt with `[needs update: dlt>=...]`.
3. **Local changes**: `git diff -- <source>/`, or ask the user. A local change may cause the issue, and it blocks automatic updates.

## Update a verified source

Only after the user agrees:
1. **Plan from the Upgrade lines.** Read the **Upgrade** line of every version between the installed one and the new one, and plan what they require: a reload or `refresh="drop_resources"`, `abort-packages` after a failed run, renamed arguments or tables. **Breaking** entries change tables, arguments or imports. For a copy without `version.py`, follow the Upgrade line of the first numbered version.
2. **Run init again:** `uv run dlthub --non-interactive pipeline init <source> <destination>`.
   - It updates the source files the user did not change.
   - For files the user changed, init asks whether to Skip, Apply (local changes are lost) or Merge (update only the unchanged files). `--non-interactive` picks Skip, so nothing changes.
   - In that case, ask the user to run `uv run dlthub pipeline init <source> <destination>` in their own terminal and make the choice there.
3. **Install the dependencies** that init reports.
4. **Run the pipeline**, applying what the Upgrade lines require.
