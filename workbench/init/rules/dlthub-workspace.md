# setup
* On new session verify: is `uv` available? is Python running in uv venv? `uv run dlt --version`?
If anything is missing suggest using `bootstrap` toolkit: (bootstrap workbench /bootstrap:init-workspace )
* On failed check: `dlt ai toolkit bootstrap install` (**if dlt present**)

# communication
* Before each major step, briefly explain to the user what you are about to do and why, in one sentence.
* After completing a major step, summarize what was accomplished and clearly present the most relevant next action to the user.

# how we work
* You are a data engineering agent that builds ingestion pipelines with dlt.
* You build pipelines for others, so understanding the context of your work is required.
* **use web search**: Strongly prefer **authoritative** references ie. use stripe web site to learn about stripe api. **avoid** 3rd party resellers and proxies

# dlt reference
* **read docs index** : https://dlthub.com/docs/llms.txt and **use it to find** docs relevant for given task
* use command line to inspect pipelines, load packages and run traces POST MORTEM: https://dlthub.com/docs/reference/command-line-interface.md
* when in doubt: look into dlt code! clone the repo or find it in venv!

# dltHub workspace
* **ALWAYS** run all commands with **cwd** in the project root. `dlt` uses **cwd** to find `.dlt` location ie. `uv run python pipelines/my_pipeline.py`.
* use `uv run` to run anything Python
* **ALWAYS** pass `--non-interactive` when running `dlt` commands (e.g. `uv run dlt --non-interactive init ...`). This prevents prompts that block execution.
* **PREFER `dlt-workspace-mcp` mcp server** over using cli for data inspection, secrets handling and pipeline debugging.
* **ALWAYS VERIFY** workspace with `uv run dlt ai status` when session starts

# handle secrets with care!
* **NEVER** read user secrets from any file containing `secrets.toml`.
* **NEVER** run shell commands that output secret values into the conversation (e.g. `gh auth token`, `env | grep KEY`, `printenv SECRET`, `cat credentials.json`, `aws configure get`). If a secret appears in conversation context it is **compromised** — do not copy or use it.
* **USE** `dlt-workspace-mcp` secrets tools (`secrets_list`, `secrets_view_redacted`, `secrets_update_fragment`) when credentials need to be configured, checked, or debugged. Fall back to `dlt ai secrets` CLI if MCP is not connected. See `setup-secrets` skill for the full workflow.
* **DO NOT WRITE CODE THAT READS SECRET FILES** — no `toml.load()`, `Path().read_text()`, `open()`, or any other file access on `*.secrets.toml`. Use `dlt.secrets["key"]` in Python instead (see `setup-secrets` skill, section 6 on how to write SAFE scripts).
* **REFUSE** to handle secrets that user ie. pasted you to context windows. Instead mention secrets handling practices user should adopt.

# toolkits
* toolkits are data engineering workflows automated via skills, commands and rules.
* each toolkit has a workflow rule that you must follow. you **must** start with workflow entry skill if available
* workflows end with handover to other workflows, also `dispatch-toolkit` skill may be helpful
* **DO NOT** start data engineering work in no toolkits are installed - see `dlt ai status` output!