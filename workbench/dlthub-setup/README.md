# dltHub Setup

dltHub Setup is the entry point to the dltHub AI harness. It sets up a dltHub workspace in your project, then installs the toolkit for your task. A toolkit gives your coding assistant the skills, rules and MCP server for one kind of data work, for example a REST API pipeline.

Works in Claude Code, Cursor and Codex.

## What it does

The plugin has one skill, `setup-dlthub-workspace`. The skill:

1. Checks what is installed: `uv`, `dlt[hub]` and the `init` toolkit.
2. Shows you a plan and asks you to approve it.
3. Installs `uv` if it is missing.
4. Runs `uvx dlthub-init@0.3.0` to install `dlt[hub]` and create the workspace.
5. Runs `dlthub ai init` to install the `init` toolkit.
6. Hands over to `dlthub-router`, which installs the toolkit for your task with `dlthub ai toolkit install`.

All toolkits come from the `dlthub` CLI, so your project gets one copy of each toolkit.

## What it runs and downloads

The plugin holds only instructions. It has no hooks, no MCP server and no code of its own. The skill asks you to approve its plan, then runs these commands in your project:

- To install `uv`, on macOS and Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`. On Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`. Both scripts come from astral.sh.
- `uvx dlthub-init@0.3.0` downloads `dlthub-init` 0.3.0 from PyPI. It installs `dlt[hub]` from PyPI and writes `.dlt/`, `.mcp.json` and skills in `.agents/skills/`. It sends usage telemetry. To turn it off, ask the skill to add `--no-telemetry`.
- If your project already has a `pyproject.toml`, `uv add "dlt[hub]" "fastmcp>=3.1.0"` adds the two dependencies from PyPI.
- `dlthub ai init` and `dlthub ai toolkit install` download the toolkits from the `dlt-hub/dlthub-ai-harness` repository on GitHub. They write files to your agent config folder, for example `.claude/`.

The skill reads files in your project folder to check what is installed. It does not upload them.

## How to use it

Install the plugin, then say what you want to build, for example:

- "Set up dlthub"
- "Load data from the Stripe API into DuckDB"
- "Build a pipeline from my Postgres database"

You can also run the skill directly with `/setup-dlthub-workspace`.

After the install, reload or restart your coding assistant to load the new skills, rules and MCP server. The skill tells you the step for your assistant.

## Requirements

- macOS, Linux or Windows.
- Internet access to install `uv` and the `dlt[hub]` Python package.
- A project folder. The skill works in an empty folder and in a folder with a `pyproject.toml`.

## Documentation and support

- Documentation: https://dlthub.com/docs/hub/ai-harness/introduction
- Support: https://dlthub.com/contact
- Privacy policy: https://dlthub.com/privacy-policy
- Terms: https://dlthub.com/terms

## License

This plugin is licensed under the Apache License 2.0. See `LICENSE`.
