---
name: add-api-change-source
description: Add or fix the release notes source of one REST API for the api-change-monitor background agent, as a workspace entry in .dlt/config.toml. Use when the agent's report says an API's release notes were unknown, not found, guessed or found by web search, when Scope lists a coverage gap, or when the user points to an API's changelog or wants a source pinned, filtered by feed topic or read per release. Do NOT use to deploy or schedule the agent (dlthub-platform workflow), to act on a finding it reported (adjust-endpoint, new-endpoint), or to debug a failed agent run (debug-deployment).
---

# Add an API's release notes source

The `api-change-monitor` agent finds the APIs a workspace calls and reads their release notes
on its own: from its built-in source list, from common changelog paths, or by a web search in
the run. This skill handles the APIs where that is not good enough. It finds the official
source, proves the agent can read it, and saves it as a workspace entry that the agent reads
on every run, before any guess or search.

**Reference**: background agents https://dlthub.com/docs/hub/ai-harness/introduction.md,
deployments https://dlthub.com/docs/hub/pipeline-operations/deployments.md

The agent's `AGENT.md`, under `.claude/dlthub/agents/dlthub-platform/api-change-monitor/`,
says what the model reads for each API, and its `registry.py` holds the built-in sources.

The helper `check_source.py` next to this file runs the agent's own reader. Run it from the
workspace root; `<skill dir>` is this skill's folder, `.claude/skills/add-api-change-source`
for Claude Code.

## 1. Pick the API

Start from what the user names, or from the agent's last report:

```bash
dlthub job runs result <agent job> --json
```

Look for `sources` entries with `origin` `guessed`, `searched` or `not_found`, and for the
`Coverage gaps` line in the summary's Scope. Then see what the agent finds in the code:

```bash
uv run python <skill dir>/check_source.py apis
```

It lists each API with its hosts, the files that call it and its current source. Note the
hosts exactly as printed: the entry needs them. An API called only through an SDK, with no
URL in the code, is not listed; ask the user which SDK module calls it.

## 2. Find the official release notes

Search for the provider's API changelog, release notes, deprecation schedule or versioning
policy. Open each candidate page yourself before choosing it.

- **Official only.** The page sits on the provider's own domain. No blogs, forums,
  aggregators or mirrors.
- **The API, not the product.** An API changelog beats a product "what's new" page.
- **Machine-readable first.** In this order: an RSS or Atom feed, a markdown variant (try the
  page URL with `.md`), a page with one dated heading or table row per change, a
  per-release page with no dates.
- **Several pages when the provider splits them.** Release notes and a separate deprecation
  schedule are two URLs of the same entry.

## 3. Prove the agent can read it

```bash
uv run python <skill dir>/check_source.py check <name> <url>
```

It prints the format, the dated notes newest first, and for a feed its categories. Exit code
0 means the agent can date the notes.

| what it shows | do |
|---|---|
| dated notes, newest entry recent | use the url |
| a warning that a large page gave few notes | the reader misses most entries: look for a feed or a `.md` variant, and use the page only if none exists |
| a feed mixing products | rerun with `--topics` naming the categories that cover the API, and keep them |
| `cannot date this page` | try the feed, the `.md` variant or another page of the provider |
| one undated note, a page per release | rerun with `--version` and a regex whose one group captures the release, such as `Release (\d{4}\.\d)` |
| newest entry months old | ask the user whether the API is quiet or the page has moved |
| fetch fails | the provider may block scripts; try another page, or tell the user the agent will fall back to search |

Stop at a page the helper can date. Never save a URL it cannot read.

## 4. Save the entry

Add a section to `.dlt/config.toml` in the workspace root, never to a `secrets.toml`: the URLs
are public and the file deploys with the workspace.

```toml
[api_change_monitor.sources.<name>]
hosts = ["api.acme.io"]          # hosts as `check_source.py apis` printed them; `*.` allowed
urls = ["https://developers.acme.io/page/changelog"]
topics = []                       # feed categories to keep; empty keeps every item
version = ""                      # regex with one group, only for pages without dates
modules = []                      # SDK modules that call the API when the code has no URL
```

- `<name>` is short and lowercase. It is the name in the agent's report and in its `apis`
  input.
- An entry with the name of a built-in API replaces that entry for this workspace. Say so to
  the user when it happens.
- Leave out the keys you do not need; `hosts` and `urls` are the ones that matter.
- Never edit the agent's own files under `.claude/dlthub/agents/`: a toolkit reinstall
  replaces them.

## 5. Show what the agent will read

```bash
uv run python <skill dir>/check_source.py window <name> --since <YYYY-MM-DD>
```

It prints the API line as the model will see it, ending "(the workspace's own source)", the
release notes of the window and the titles the hook rules out. Show the user the API line and
the first notes.

## 6. Deploy

The entry reaches the platform with the workspace's configuration. Ask before deploying, then:

```bash
dlthub deploy
```

The next run reads the new source in its first step. Its report lists the source with
`origin: configured`.

## Hand back

- A source that would serve every workspace, an official feed of a widely used API, can also
  go into the agent's built-in list. Offer the user a pull request adding it to `registry.py`
  of the dlthub-platform toolkit in the AI harness repo; never edit the installed copy.
- To act on what the agent reports, go to **rest-api-pipeline**: `adjust-endpoint` or
  `new-endpoint`.
