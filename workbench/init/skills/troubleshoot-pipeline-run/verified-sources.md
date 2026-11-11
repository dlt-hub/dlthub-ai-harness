# Verified sources: copies, maintenance notes and updates

Verified sources: https://dlthub.com/docs/dlt-ecosystem/verified-sources.md
Source code and the latest notes: https://github.com/dlt-hub/verified-sources (folder `sources/<source>/`)

## What `dlthub pipeline init` copies

`dlthub pipeline init <source> <destination>` copies a verified source into the project:
- its code, in the `<source>/` folder, with `README.md` and, for a versioned source, `version.py`
- an example script, `<source>_pipeline.py`
- a record in `.dlt/.sources`: `last_commit_sha` and `last_commit_timestamp` of the copy, a hash of each file, and `dlt_version_constraint`

The copy is the user's code. Upgrading dlt does not change it.

## The maintenance notes in `<source>/README.md`

They are written for developers and coding agents:
- **Changelog**: one entry per version.
  - The **Upgrade** line says whether the upgrade is safe, whether the incremental state carries over, and what to reload.
  - The entries are marked **breaking**, fixed, changed or new, and name the resource, argument or backend they affect.
- **Operations**: known limits and failure modes, with the error each one raises, the versions of the source system and libraries they apply to, and how the backends differ.
- **Extension points**: where in the code to add a type, a table or a field.

A copy without `version.py` predates 1.0.0 and has no maintenance notes. `.dlt/.sources` tells which commit it came from. Read the latest notes upstream instead.

## Checks before you debug or change the source code

1. **Newer version**: compare the installed `__version__` with the Changelog at `https://raw.githubusercontent.com/dlt-hub/verified-sources/master/sources/<source>/README.md`. The entries above the installed version are fixes the copy does not have.
2. **dlt version**: the installed dlt (`uv run python -c "import dlt; print(dlt.__version__)"`) must satisfy `dlt_version_constraint` in `.dlt/.sources`. `uv run dlthub --non-interactive pipeline init --list-sources` marks a source that needs a newer dlt with `[needs update: dlt>=...]`.
3. **Local changes**: `git diff -- <source>/`, or ask the user. A local change may cause the issue, and it blocks automatic updates.

## Update a verified source

Only after the user agrees:
1. **Plan from the Upgrade lines.** Read the **Upgrade** line of every version between the installed one and the new one, and plan what they require: a reload or `refresh="drop_resources"`, `abort-packages` after a failed run, renamed arguments or tables. **Breaking** entries change tables, arguments or imports.
2. **Run init again:** `uv run dlthub --non-interactive pipeline init <source> <destination>`.
   - It updates the source files the user did not change.
   - For files the user changed, init asks whether to Skip, Apply (local changes are lost) or Merge (update only the unchanged files). `--non-interactive` picks Skip, so nothing changes.
   - In that case, ask the user to run `uv run dlthub pipeline init <source> <destination>` in their own terminal and make the choice there.
3. **Install the dependencies** that init reports.
4. **Run the pipeline**, applying what the Upgrade lines require.
