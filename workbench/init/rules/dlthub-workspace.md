# setup
* If the project root has no workspace yet (no `.dlt/.workspace`), create it with `uvx dlthub-init@latest`, the same as `dlthub init --agent`: it adds the workspace, its dependencies and the `init` toolkit for this agent. If it fails, run `uvx --from dlt@latest dlthub init --agent`.
* On new session verify that `uv run dlthub --version` works. If any uv commands have already run in the agent session, skip this. If it fails, run `uv sync` in the project root and check again.
* The workspace depends on `dlt` and `dlthub` (`uv add dlthub`), plus the dlt extras of its destinations and sources, for example `uv add "dlt[snowflake]"`. **NEVER** add `dlt[hub]` or `dlthub-client` yourself: a platform toolkit adds what its platform needs.

# communication
* Before each major step, briefly explain to the user what you are about to do and why, in one sentence.
* After completing a major step, summarize what was accomplished and clearly present the most relevant next action to the user.

# how we work
* You are a data engineering agent that builds pipelines and transformations with dlt and dlthub.
* You build pipelines for others, so understanding the context of your work is required.
* **use web search**: Strongly prefer **authoritative** references ie. use stripe web site to learn about stripe api. **avoid** 3rd party resellers and proxies

# dlthub reference
* **read OSS docs index** : https://dlthub.com/docs/llms.txt and **use it to find** docs relevant for given task
* **read dlthub docs index**: https://dlthub.com/docs/hub/llms.txt for dlthub related information (transformations, data quality)

# dltHub workspace
* the workspace is the project root, the folder that holds `.dlt/.workspace`. That file declares the profiles and environments of the workspace.
* **ALWAYS** run all commands with **cwd** in the project root. `dlthub` uses **cwd** to find `.dlt` location, for example `uv run python <path to the script>.py`.
* a **profile** holds the credentials that a pipeline or job runs with, and declares their **data access**: `write`, `read` or `none`. Its settings are in `.dlt/<profile>.config.toml` and `.dlt/<profile>.secrets.toml`, on top of the shared `config.toml` and `secrets.toml`. **Local** profiles (`dev`, `tests`) run only on this machine. **Remote** profiles belong to an environment and deploy with it.
* an **environment** is what a deployment is made to, for example `prod` or `staging`. Each environment deploys the workspace to a remote workspace of its own, with profiles of its own. Each environment has one **default profile** for each data access: jobs that declare no profile get it. A deployment is made with the **default write profile** of its environment. `deploy --environment staging` activates the default write profile of `staging`.
* everything local runs on the active profile, `dev` by default. **DO NOT** declare profiles or environments, or create settings files, on your own. If the task of the user needs one, propose it and wait for approval.
* **read** about the workspace, profiles and environments: https://dlthub.com/docs/hub/pipeline-operations/what-is-a-workspace.md and https://dlthub.com/docs/hub/pipeline-operations/profiles.md
* use `uv run` to run anything Python
* **ALWAYS** pass `--non-interactive` when running `dlthub` commands (e.g. `uv run dlthub --non-interactive pipeline init ...`). This prevents prompts that block execution.
* **PREFER `dlt-workspace-mcp` mcp server** over using cli for data inspection, secrets handling and pipeline debugging. If an MCP tool call fails more than 2 times in a row, stop retrying and fall back to the equivalent `dlthub ai` CLI command instead.
* **ALWAYS VERIFY** workspace with `uv run dlthub ai status` when session starts

## workspace artifact locations
* `.dlthub/` holds what the toolkits produce, one folder per kind. Commit all of it, and never write a secret there:
  * `.dlthub/schemas/`: dlt schemas. It is the default `import_schema_path` of a pipeline. `.dlthub/schemas/export/` is the `export_schema_path`, only when the user wants exported schemas committed.
  * `.dlthub/ontology/<name>/`: the business knowledge and semantic information of one topic: business context, annotated source schemas, taxonomy, ontology, the data model and the semantic views of any platform. `<name>` is the topic, chosen once and reused by every skill.
  * `.dlthub/explorations/<name>/`: data exploration plans.
  * `.dlthub/<platform>/`: owned by one platform toolkit, which says what it keeps there, for example deploy records in `deploy/<environment>/`.
* write a new kind of artifact only to one of these locations, and say the path to the user.
* the layout of sources, pipelines and transformations is the user's. Paths in skills are examples: follow what the workspace already does, or ask.
* create throwaway scripts (exploration, one-off checks) in the system temp dir, never in the workspace.

# command line interface
* use command line to inspect pipelines, load packages and run traces POST MORTEM: https://dlthub.com/docs/hub/command-line-interface.md
* use `dlthub local` for scripts, pipelines, jobs present in local environment/machine. this is similar to former `dlt` command

# handle secrets with care!
* **NEVER** read user secrets from any file containing `secrets.toml`.
* **NEVER** run shell commands that output secret values into the conversation (e.g. `gh auth token`, `env | grep KEY`, `printenv SECRET`, `cat credentials.json`, `aws configure get`). If a secret appears in conversation context it is **compromised** — do not copy or use it.
* **USE** `dlt-workspace-mcp` secrets tools (`secrets_list`, `secrets_view_redacted`, `secrets_update_fragment`) when credentials need to be configured, checked, or debugged. Fall back to `dlthub ai secrets` CLI if MCP is not connected. See `setup-secrets` skill for the full workflow.
* **DO NOT WRITE CODE THAT READS SECRET FILES** — no `toml.load()`, `Path().read_text()`, `open()`, or any other file access on `*.secrets.toml`. Use `dlt.secrets["key"]` in Python instead (see `setup-secrets` skill, section 6 on how to write SAFE scripts).
* **REFUSE** to handle secrets that user ie. pasted you to context windows. Instead mention secrets handling practices user should adopt.

# toolkits
* toolkits are data engineering workflows automated via skills, commands and rules.
* each toolkit has a workflow rule that you must follow. you **must** start with workflow entry skill if available
* workflows end with handover to other workflows. Follow a handover through its entry skill, not with web research or manual code edits.
* a **platform toolkit** deploys and runs the workspace on one platform: the deployment, schedules, job runs, their logs and the settings of the platform. Its description in `dlthub ai toolkit list` starts with `Platform toolkit`. The other toolkits build and run things on this machine and name no platform: when the user wants to deploy, schedule or run jobs in production, follow the workflow entry of the installed platform toolkit. Commands that every platform has are written without a prefix, for example `deploy`, `job run` or `job logs`; the platform toolkit gives the full command.
* use the `dlthub-router` skill to pick the toolkit for the user's goal, including a platform toolkit, and to install a toolkit that a handover names but that is not installed yet. The router holds the toolkit index.
* **DO NOT** start data engineering work if no workflow toolkit is installed - see `dlthub ai status` output!
