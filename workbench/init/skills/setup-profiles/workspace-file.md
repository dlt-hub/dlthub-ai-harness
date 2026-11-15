# Edit `.dlt/.workspace`

dlt, `dlthub profile add` and `dlthub profile add-environment` write `.dlt/.workspace`. Edit it only for the changes
below. Before you make a change, show it to the user. Then run `dlthub profile list`. Never change `engine_version`.

dlt validates the file on every command. It reports a wrong or missing key first, then the other problems together,
each with its fix. Until the file is valid, every `dlthub` command stops.

## The built-in declaration

```yaml
engine_version: 1
environments:
  prod:
    default: true
    strict_access: false
    profiles:
      prod: {data_access: write, default: true}
      access: {data_access: read, default: true}
local_profiles:
  dev: {data_access: write, default: true}
  tests: {data_access: write}
```

A profile under `environments.<env>.profiles` is remote, a profile under `local_profiles` is local. `data_access` is
`write`, `read` or `none`. In each environment, one profile of each data access has `default: true`, and one profile
has write data access. `dlthub profile list` marks the defaults.

## Change the default profile of a data access

An environment can have more profiles with the same data access, for example `access` and `sensitive-access` with
read data access. One of them is the default: jobs of that data access that declare no profile get it. The default
with write data access is the default write profile: deployments are made with it.

1. Make sure that the new default has settings files, unless it has no data access. A default without settings files
   does not count.
2. Move `default: true` from the old default to the new one. Keep exactly one default for each data access.
3. Tell the user which jobs change their profile: every job of that data access that declares no profile.
4. If you change the default write profile, the deployment module runs with the new one, and its
   `[jobs.<module>]` settings apply. `deploy --environment <env>` then activates it.

## Rename a profile

For example, `dlthub profile add-environment staging` names the default write profile `staging-write`, and the user
wants `staging`. To rename a profile:

1. Rename its key. Its `default: true` stays with it.
2. Rename `.dlt/<old>.config.toml`, `.dlt/<old>.secrets.toml`, `.dlt/state/<old>/` and `.dlt/data/<old>/`. Do not
   read the secrets file.
3. If `.dlt/profile-name` records the old name, update it. An undeclared active profile stops every command.
4. Replace the old name in the code and in CI: `require={"profile": ...}`, `switch_profile(...)`, `--profile`,
   `WORKSPACE__PROFILE`.
5. Move the settings that the deployment platform keeps per profile name, as its toolkit says. The next deployment
   ships the profile under its new name.

## Make an environment strict or not strict

[SKILL.md](SKILL.md) says what strict about access means and which data access each job declares. To make an
environment strict:

1. For each data access that its jobs declare, make sure that the environment has a default profile with settings
   files. A profile without data access needs no settings files. Add the missing ones:
   - read: `dlthub profile add <env>-read --access read --env <env>`, with read-only credentials.
   - none: `dlthub profile add <env>-none --access none --env <env>`.
2. A job that declares a profile must declare one with exactly its data access and with settings files.
3. Set `strict_access: true`.
4. Run `deploy --dry-run --environment <env>`. It fails on each job without a profile of its data access, and names
   the fix.

To make an environment not strict, set `strict_access: false` or remove the key. Then a job can get a default profile
with more data access than it declares. The next deployment warns about each such job.

## Do not rename `prod`

Keep the environment `prod` and its profiles `prod` and `access`. If the user wants other names, explain the cost and
ask first:

- An emptied file, or a migrated older one, declares `prod` again.
- The files, folders and platform settings of `prod` and `access` must move.
- The docs and the platform toolkits name `prod` and `access`.

To deploy production somewhere else, add an environment next to `prod`.

## Change the default environment or the default local profile

Move `default: true` to another environment or local profile. Keep exactly one of each.

CAUTION: Before you move the default environment, give each environment a `[workspace.environment.<env>]` section in
`config.toml`. The default environment takes the shared `[runtime] workspace_id` and workspace name. Without its own
section, an environment can deploy to the remote workspace of another one.

## Remove a profile or an environment

1. If you remove the default environment, move `default: true` first.
2. If you remove a default profile, first move `default: true` to another profile of its data access. Every
   environment keeps a profile with write data access.
3. Remove the key. An environment takes its profiles with it.
4. After the user agrees, remove the settings files of the removed profiles. Never read a secrets file.
5. If `.dlt/profile-name` records a removed profile, remove that file. Remove the name from the code.
6. For an environment, remove `[workspace.environment.<env>]` from `config.toml`.

## Start over

Empty the file. Do not delete it: dlt finds the workspace by this file. dlt then declares the built-in profiles again.
Each other profile with settings files, or recorded in `.dlt/profile-name`, becomes an environment of its own with
write data access. The environments that you declared are lost.
