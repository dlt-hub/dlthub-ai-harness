# Profiles
1. Locally pipelines and datasets run on `dev` profile.
2. On runtime pipelines (batch jobs) run on `prod` profile
3. On runtime notebooks (interactive jobs) run on `access` profile. if not defined they run on `prod` profile.
4. If user pins a different profile - it is used to run pipelines and datasets locally.
5. Get workspace info (via cli or mcp tool) to see a list of profiles. **configured** profiles are one

# Secrets and configs
1. Profiles have corresponding secrets and configs.
2. `config.toml` and `secrets.toml` apply to **all profiles**. Keep only common settings in them
3. `dev.config.toml` and `dev.secrets.toml` define settings specific to `dev` profile
4. Settings in profile-scoped toml files overwrite workspace-scoped toml files.
5. Use `dlt ai secrets` as usual — `update-fragment` requires `--path`, so always pass the right file! `dlt ai secrets list` when in doubt.

# Switch profile
* set `WORKSPACE__PROFILE` env variable when running Python commands to temporarily switch profile
* pin profile with `dlt profile <name> pin` to change profile in this session. **require to switch mcp server**

**Reference** https://dlthub.com/docs/hub/core-concepts/profiles-dlthub.md