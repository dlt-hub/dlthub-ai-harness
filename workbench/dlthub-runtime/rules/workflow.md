1. Verify workspace setup:
- `.dlt/.workspace` file must be present to enable dlthub runtime cli, and profiles
- `pyproject.toml` is strongly recommended.
- `dlthub` and `dlt-runtime` dependencies must be installed. use `uv pip install dlt[hub]` if not
- if adding `dlt` to `pyproject.toml` you must pin the exact installed version (`==`) — `uv add` may downgrade pre-release versions
2. Use `dlt runtime` to interact with dlthub runtime.
3. Login user using cli - may require browser interaction
- `dlt runtime login` opens a device-code OAuth flow (user visits URL + enters code in browser)
- After auth, CLI prompts to select or create a remote workspace (interactive — needs piped input if non-interactive: `printf '1\n' | dlt runtime login`)
- Creating a new workspace requires three inputs: selection (`0`), name, description (can be empty)
- The selected workspace ID is stored in `config.toml` under `[runtime] workspace_id`
- To **switch workspaces**: `dlt runtime logout`, remove `workspace_id` from `config.toml`, then `dlt runtime login` again
4. Allow user to work locally using `dev` profile
5. Deploy: react to users intent to deploy pipelines, transformations and notebooks by using the right skill
- During deployment be aware of `prod` profile and secrets which runtime will use
- You will change the `dev` destination (ie. duckdb) to production version. Preferably using named destinations!
6. Maintain: react to user requests to inspect runtime jobs, logs and other runtime entities

References:
* **Additional documentation** https://dlthub.com/docs/hub/llms.txt
* **Workspace and runtime cli**  https://dlthub.com/docs/hub/command-line-interface.md
* **Runtime overview**  https://dlthub.com/docs/hub/runtime/overview.md