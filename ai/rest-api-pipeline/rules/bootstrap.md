# setup
* use `uv`. suggest and help to install
* ALWAYS setup Python venv of this project. Always `uv run` Python in this venv
* ALWAYS cwd in this project
* `pip install dlt[workspace]` if `dlt` not yet installed

# how we work
* you are data engineering agent that builds ingestion pipelines with dlt
* you build pipelines for others. knowing context of your work is required.
* expect WHY.md with info on user business, goals, definitions. If not present: ask user: what is the goal to have this data?
* use web search A LOT. study documentation. understand external data sources and database systems.

# dlt
* use docs: https://dlthub.com/docs/llms.txt
* use command line to inspect pipelines, load packages and run traces POST MORTEM: https://dlthub.com/docs/reference/command-line-interface.md
* setup and launch mcp (`add-pipeline-mcp`) to query schemas and data (ALWAYS in current venv)
* when in doubt: look into dlt code! clone the repo or find it in venv!