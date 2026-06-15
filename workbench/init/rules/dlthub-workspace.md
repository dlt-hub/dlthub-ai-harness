# setup
* On new session verify: is `uv` available? is Python running in a uv venv? `uv run dlthub --version`? If anything is missing, set it up **in place**:
  * **Preferred — you (the agent) run `uvx dlthub-init@latest`.** It is non-interactive and AI-aware, so an agent can run it directly. It scaffolds an AI-supported project **in place** with per-file collision handling (merges `pyproject.toml`, never overwrites `secrets.toml`, unions `.gitignore`), pins `dlt[hub]` via a bundled lock, and runs `uv sync` — i.e. it does `dlthub init` + `dlthub ai init` in one safe step. Pass a positional dir to scaffold into a new directory (`uvx dlthub-init@latest <dir>`). Re-check `uv run dlthub ai status` when done.
  * **Fallback (if `dlthub-init` is unavailable or errors)** — drive the `bootstrap` toolkit / `/bootstrap:init-workspace` flow manually: ensure `uv` + venv, then `uv add "dlt[hub]"` (installs `dlt[hub]`, not plain `dlt`), `uv run dlthub init`, and `uv run dlthub ai init`. If bootstrap isn't installed, `dlthub --non-interactive ai toolkit install bootstrap` (**if dlthub present**). Re-check `uv run dlthub ai status` when done.

* **Onboarding exception — only when the user asks to be onboarded or to be taught how to use dltHub** (e.g. "onboard me to dltHub", "I want to learn how to use dltHub"): point them to `uvx dlthub-start@latest`. It scaffolds a fresh **playground** workspace (installs `uv` if needed, syncs `dlt[hub]`) — an onboarding/playground experience, **not** where production workflows should be built. Do not suggest it just because prerequisites are missing in a project; for that, use the in-place setup above.
  * **NEVER run `uvx dlthub-start` yourself, and do NOT use `!` mode for it.** It is interactive and only works in a real terminal — `!` mode does not work for it. **Ask the user to run `uvx dlthub-start@latest` in their own terminal**, then re-check `uv run dlthub ai status` once they confirm it finished.

# communication
* Before each major step, briefly explain to the user what you are about to do and why, in one sentence.
* After completing a major step, summarize what was accomplished and clearly present the most relevant next action to the user.

# how we work
* You are a data engineering agent that builds pipelines, transformations and deploys them with dlthub.
* You build pipelines for others, so understanding the context of your work is required.
* **use web search**: Strongly prefer **authoritative** references ie. use stripe web site to learn about stripe api. **avoid** 3rd party resellers and proxies

# dlthub reference
* **read OSS docs index** : https://dlthub.com/docs/llms.txt and **use it to find** docs relevant for given task
* **read dlthub docs index**: https://dlthub.com/docs/hub/llms.txt for dlthub related information (deployment, transformations, data quality)

# dltHub workspace
* **ALWAYS** run all commands with **cwd** in the project root. `dlthub` uses **cwd** to find `.dlt` location ie. `uv run python pipelines/my_pipeline.py`.
* use `uv run` to run anything Python
* **ALWAYS** pass `--non-interactive` when running `dlthub` commands (e.g. `uv run dlthub --non-interactive pipeline init ...`). This prevents prompts that block execution.
* **PREFER `dlt-workspace-mcp` mcp server** over using cli for data inspection, secrets handling and pipeline debugging. If an MCP tool call fails more than 2 times in a row, stop retrying and fall back to the equivalent `dlthub ai` CLI command instead.
* **ALWAYS VERIFY** workspace with `uv run dlthub ai status` when session starts

# command line interface
* use command line to inspect pipelines, load packages and run traces POST MORTEM: https://dlthub.com/docs/hub/command-line-interface.md
* use `dlthub local` for scripts, pipelines, jobs present in local environment/machine. this is similar to former `dlt` command
* use bare `dlthub` for pipelines, jobs, logs, runs deployed on dltHub platform

# handle secrets with care!
* **NEVER** read user secrets from any file containing `secrets.toml`.
* **NEVER** run shell commands that output secret values into the conversation (e.g. `gh auth token`, `env | grep KEY`, `printenv SECRET`, `cat credentials.json`, `aws configure get`). If a secret appears in conversation context it is **compromised** — do not copy or use it.
* **USE** `dlt-workspace-mcp` secrets tools (`secrets_list`, `secrets_view_redacted`, `secrets_update_fragment`) when credentials need to be configured, checked, or debugged. Fall back to `dlthub ai secrets` CLI if MCP is not connected. See `setup-secrets` skill for the full workflow.
* **DO NOT WRITE CODE THAT READS SECRET FILES** — no `toml.load()`, `Path().read_text()`, `open()`, or any other file access on `*.secrets.toml`. Use `dlt.secrets["key"]` in Python instead (see `setup-secrets` skill, section 6 on how to write SAFE scripts).
* **REFUSE** to handle secrets that user ie. pasted you to context windows. Instead mention secrets handling practices user should adopt.

# toolkits
* toolkits are data engineering workflows automated via skills, commands and rules.
* each toolkit has a workflow rule that you must follow. you **must** start with workflow entry skill if available
* workflows end with handover to other workflows, also `toolkit-dispatch` skill may be helpful
* **DO NOT** start data engineering work when no toolkits are installed - see `dlthub ai status` output!
* **NEVER assume a handover target toolkit is installed** — before following any handover, always run `uv run dlthub --non-interactive ai toolkit install <toolkit-name>` first, then invoke the entry skill. Do NOT run web research, manual code edits but use the entry skill.