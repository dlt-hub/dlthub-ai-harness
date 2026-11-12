---
name: init-workspace
description: "Set up dlthub in this project and install the toolkit for the user's task. Use when the dltHub workspace rules of the `init` toolkit are not in your context and not on disk (dlthub is not set up, or `dlthub ai init` has not run) and the user wants to build anything with dlt or dlthub: 'set up dlthub', 'init workspace', 'load data from Stripe', 'build a REST API pipeline', 'ingest from Postgres', 'load CSVs from S3', 'transform my data', 'deploy a pipeline', 'what can I build with dlthub'. Installs uv, dlt[hub] and the init toolkit with the dlthub CLI, then hands over to `dlthub-router` to install the matching workflow toolkit. Works in Claude Code, Cursor, Codex, Copilot and Gemini. Do NOT use when the dltHub workspace rules are in your context, or on disk in `.claude/rules/init-dlthub-workspace.md` or `AGENTS.md`: dlthub is set up, use `dlthub-router` or the entry skill of the toolkit. Do NOT use when the user asks to be onboarded or to learn dlthub: point them to `uvx dlthub-start@latest`."
---

# Set up dlthub and install a toolkit

Set up dlthub in the current project. Then hand over to `dlthub-router` from the `init` toolkit, which installs the toolkit that the user needs.
Use the `dlthub` CLI for every install, so that each toolkit has only one copy.

Docs:
- dltHub AI workflow: https://dlthub.com/docs/dlt-ecosystem/llm-tooling/llm-native-workflow
- `dlthub-init`: https://pypi.org/project/dlthub-init/
- uv install: https://docs.astral.sh/uv/getting-started/installation/

> **Onboarding exception.** If the user asks to be onboarded, or to learn how to use dltHub, do not run this skill.
> Ask the user to run `uvx dlthub-start@latest` in their own terminal. It creates a separate **playground** workspace.
> Never run `uvx dlthub-start` yourself, and do not use `!` mode for it. It needs interactive authentication.

## Step 1: Check what is installed

Run these checks in order. Do not install anything yet.

1. Check if the dltHub workspace rules of the `init` toolkit are installed. Check your context and the files on disk:
   - The rules are in your context (project rules or `AGENTS.md`).
   - Claude Code: `.claude/rules/init-dlthub-workspace.md` exists.
   - Cursor: `.cursor/rules/init-dlthub-workspace.mdc` exists.
   - Codex, Copilot and Gemini: `AGENTS.md` contains `init-dlthub-workspace`.
   - If one of these is true, `init` is installed. Stop this skill. Use `dlthub-router` or the entry skill of the matching toolkit.
   - The files are on disk but not in your context after `/reload-skills` and before the restart. They still count.
2. Run `uv --version`. If it fails, `uv` is missing.
3. Run `test -f pyproject.toml`. Note if `pyproject.toml` exists. Step 3 uses this result.
4. Run `uv run --no-sync dlthub --version`. If it fails, `dlt[hub]` is missing.
   - `--no-sync` does not install packages and does not write `uv.lock`. It can create an empty `.venv/`. This is expected.
5. If `dlt[hub]` is installed, run `uv run --no-sync dlthub ai status`. If it shows `dlthub ai init not yet run`, `init` is missing.
   - A project from `uvx dlthub-init@latest` has some `init` skills in `.agents/skills/`, but no rules. That is not enough.
6. Find the `--agent` value for the coding assistant that runs this skill. If you are not sure, ask the user.

| Coding assistant | `--agent` | Notes |
|---|---|---|
| Claude Code | `claude` | |
| Cursor | `cursor` | |
| Codex | `codex` | |
| GitHub Copilot | `codex` | Copilot reads `.agents/skills/`, `AGENTS.md` and `.mcp.json`. |
| Gemini CLI | `codex` | Also write `.gemini/settings.json` (Step 4). |

## Step 2: Show the plan

Show the user what is missing and what you will run:

```
dlthub setup:
  uv:              ✓ installed (x.y.z) / ✗ missing
  pyproject.toml:  exists / missing
  dlt[hub]:        ✓ installed (x.y.z) / ✗ missing
  init:            ✓ installed / ✗ missing
  task:            <task>

Actions:
  1. Install uv                                          (if missing)
  2. uvx dlthub-init@latest                              (if dlt[hub] is missing)
     + uv add "dlt[hub]" "fastmcp>=3.1.0"                (if pyproject.toml exists)
  3. dlthub ai init --agent <agent> --overwrite          (if init is missing)
  4. Write .gemini/settings.json                         (Gemini only)
  5. dlthub-router picks and installs the toolkit        (if the user has a task)
```

Ask the user to approve the plan. If the user refuses, stop.

## Step 3: Install dlthub and init

Run only the actions that the user approved.

**1. Install uv** (if missing):
- On macOS and Linux, run `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- On Windows, run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
- If `uv` is still not found, tell the user to open a new shell, because the install changes `PATH`.

**2. Install dlt[hub] and the workspace:**

Choose the commands from the result of the `pyproject.toml` check in Step 1.

If `pyproject.toml` is missing, run:

```
uvx dlthub-init@latest
```

If `pyproject.toml` exists, run:

```
uvx dlthub-init@latest
uv add "dlt[hub]" "fastmcp>=3.1.0"
```

- `dlthub-init` sets up the current folder in place. It writes `.dlt/`, `.mcp.json` and a few `init` skills in `.agents/skills/`. It does not install the rules.
- `dlthub-init` skips an existing `pyproject.toml`. Then it does not add `dlt[hub]` or `fastmcp`, but it still exits 0.
- `uv add` adds the two dependencies that `dlthub-init` skipped. `dlt[hub]` gives the `dlthub` command. `fastmcp` runs the MCP server.
- Fallback, if `dlthub-init` is not available or fails: run `uvx --from "dlt[hub]" dlthub init`.

Then run `uv run dlthub --version`.
- If it fails, stop. Show the error to the user. Do not continue with `ai init`.
- Do this check every time. The exit code of `dlthub-init` does not show if `dlt[hub]` is installed.

**3. Install init:**

```
uv run dlthub --non-interactive ai init --agent <agent> --overwrite
```

- It installs the rules, the skills and the MCP config of the `init` toolkit. This includes `dlthub-router` and the toolkit index.
- `--overwrite` replaces the old `init` skills that `dlthub-init` bundles.
- Use `--overwrite` only when `dlthub ai init` did not run before in this project. Otherwise it replaces files that the user changed.

**4. Gemini only: write `.gemini/settings.json`**

Gemini does not read `AGENTS.md` or `.mcp.json`. If `.gemini/settings.json` exists, add these keys to it and keep the other keys:

```json
{
  "context": {"fileName": ["AGENTS.md", "GEMINI.md"]},
  "mcpServers": {
    "dlt-workspace-mcp": {"command": "uv", "args": ["run", "dlthub", "ai", "mcp", "--stdio"]}
  }
}
```

**5. Check the status:**

Run `uv run dlthub ai status`. If it shows a WARNING about the MCP server, fix it before you continue:
- If the WARNING says `pip install "fastmcp"`, run `uv add "fastmcp>=3.1.0"`. Then run `uv run dlthub ai status` again.
- For a different WARNING, show it to the user and stop.

## Step 4: Hand over to dlthub-router

Skip this step if the user only asked to set up dlthub.

`dlthub-router` from `init` picks the toolkit for the task and installs it. Do not pick the toolkit yourself.
The router and the init rules are on disk now, but not in your context until the reload. Read them from the project folder:

| Coding assistant | Init rules (with the toolkit index) | Router |
|---|---|---|
| Claude Code | `.claude/rules/init-dlthub-workspace.md` | `.claude/skills/dlthub-router/SKILL.md` |
| Cursor | `.cursor/rules/init-dlthub-workspace.mdc` | `.cursor/skills/dlthub-router/SKILL.md` |
| Codex, Copilot and Gemini | `.agents/skills/init-dlthub-workspace/SKILL.md` | `.agents/skills/dlthub-router/SKILL.md` |

Follow the router to pick and install the toolkit, with these changes:
- Run its install command as `uv run dlthub --non-interactive ai toolkit install <toolkit> --agent <agent>`.
- Until the reload, use the `uv run dlthub ai` CLI instead of the `dlt-workspace-mcp` tools.
- Stop before the router hands over to the entry skill. Do Step 5 first.

## Step 5: Tell the user how to load the new files

The new skills, rules and MCP server load at session start. The agent cannot reload them itself.
The router says that no restart is needed. That is true only when `init` was loaded at session start. Here it was not.
Tell the user the step for their coding assistant:

| Coding assistant | Tell the user |
|---|---|
| Claude Code | "Run `/reload-skills` to use the new skills now. Restart the session later to load the rules and the MCP server." |
| Copilot CLI | "Trust this folder if Copilot asks. Run `/skills reload` and `/mcp reload`. Start a new session later to load `AGENTS.md`." |
| Codex | "Restart the session to load the rules and the MCP server." |
| Cursor | "Restart the session to load the new skills, rules and MCP server." |
| Gemini CLI | "Trust this folder, then restart the session. Gemini loads project skills only in a trusted folder." |

## Step 6: Continue the task

Do not wait for the reload. Continue with the handover step of `dlthub-router`:
read the workflow rule and the entry skill of the new toolkit from the project folder, and follow the entry skill with the context that you already have.
