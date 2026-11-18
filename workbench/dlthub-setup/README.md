# dltHub Setup

dltHub Setup is the entry point to the dltHub AI harness. It sets up a dltHub workspace in your project, then installs the toolkit for your task. A toolkit gives your coding assistant the skills, rules and MCP server for one kind of data work, for example a REST API pipeline.

Works in Claude Code, Cursor, Codex and CoCo (Snowflake Cortex Code).

## What it does

The plugin has one skill, `setup-dlthub-workspace`. The skill:

1. Checks what is installed: `uv`, `dlt[hub]` and the `init` toolkit.
2. Shows you a plan and asks you to approve it.
3. Installs `uv` if it is missing.
4. Runs `uvx dlthub-init@latest` to install `dlt[hub]` and create the workspace.
5. Runs `dlthub ai init` to install the `init` toolkit.
6. Hands over to `dlthub-router`, which installs the toolkit for your task with `dlthub ai toolkit install`.

All toolkits come from the `dlthub` CLI, so your project gets one copy of each toolkit.

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
