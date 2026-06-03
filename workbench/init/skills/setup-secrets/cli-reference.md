# CLI reference for dlthub secrets

Use these commands when `dlt-workspace-mcp` is not connected. All MCP tools have CLI equivalents:

| MCP tool | CLI equivalent |
|---|---|
| `secrets_list` | `dlthub ai secrets list` |
| `secrets_view_redacted` | `dlthub ai secrets view-redacted [--path <file>]` |
| `secrets_update_fragment` | `dlthub ai secrets update-fragment --path <file> '<toml>'` |

## `secrets list`

Lists project-scoped secrets files. Profile-scoped files (e.g. `.dlt/dev.secrets.toml`) appear first.

```sh
dlthub ai secrets list
```

## `secrets view-redacted`

Shows TOML structure with values replaced by `***`. Without `--path`, shows the unified merged view across all workspace secret files.

```sh
dlthub ai secrets view-redacted
dlthub ai secrets view-redacted --path .dlt/<profile>.secrets.toml
```

## `secrets update-fragment`

Merges a TOML fragment into a secrets file. Creates the file if needed, deep-merges without overwriting other sections, prints the redacted result. `--path` is required.

### Linux / macOS

Use multiline single-quoted strings — all POSIX shells (bash, zsh, sh, dash, fish) pass real newlines:

```sh
dlthub ai secrets update-fragment --path .dlt/secrets.toml '[sources.stripe]
api_key = "sk-test-xxxxxxxxxxxx"
'
```

```sh
dlthub ai secrets update-fragment --path .dlt/secrets.toml '[destination.postgres.credentials]
host = "localhost"
port = 5432
database = "analytics"
username = "loader"
password = "<paste-your-password-here>"
'
```

Profile-scoped:
```sh
dlthub ai secrets update-fragment --path .dlt/<profile>.secrets.toml '[sources.my_api]
api_key = "sk-xxxxxxxxxxxx"
'
```

### Windows

Use `\n` for newlines in a single-line string. The CLI converts literal `\n` to real newlines before parsing:

```
dlthub ai secrets update-fragment --path .dlt/secrets.toml "[sources.stripe]\napi_key = \"sk-test-xxxxxxxxxxxx\""
```

```
dlthub ai secrets update-fragment --path .dlt/secrets.toml "[destination.postgres.credentials]\nhost = \"localhost\"\nport = 5432\ndatabase = \"analytics\"\nusername = \"loader\"\npassword = \"<paste-your-password-here>\""
```
