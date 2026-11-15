# Profiles
1. Locally, pipelines and datasets run on the active profile, `dev` by default.
2. A deployment gives pipelines (batch jobs) the default write profile of its environment: `prod` for `dlthub deploy`, `staging-write` for `dlthub deploy --environment staging`.
3. A deployment gives notebooks (interactive jobs) the default profile with read data access: `access` in the `prod` environment. Until `access` has settings files, they get `prod`, and `dlthub deploy` warns.
4. **NEVER** give an agent job (`run.agent(...)`) the `prod` profile.
   - Declare no profile on an agent job. Keep `write` out of `access.data` in its agent definition. With `write`, the agent job gets the default write profile, `prod` in `prod`.
   - For every environment that an agent job deploys to, declare a profile with `none` data access: `dlthub profile add <env>-none --access none --env <env>`. The deployment gives that profile to the agent job. It needs no settings files.
   - In `prod` without a profile with `none` data access, the agent job gets `access`, or `prod` while `access` has no settings files. `dlthub deploy` warns.
   - In a strict environment without a profile with `none` data access, `dlthub deploy` fails.
   - The profile covers only the profile-scoped settings: `<profile>.config.toml`, `<profile>.secrets.toml` and variables set with `--profile`. A variable set with `--workspace` reaches every profile, so scope one an agent must not see with `--profile`. Work needing production write credentials goes in a pipeline or a plain job, not an agent.

For profiles, environments, their settings files and the active profile, use the `setup-profiles` skill (init toolkit).

**Reference** https://dlthub.com/docs/hub/pipeline-operations/profiles.md
