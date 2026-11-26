---
name: delegate-to-cortex-code
description: "Use when a Snowflake task needs the Snowflake internals and this agent is not Cortex Code: exploring what the account holds (lineage, object history, who queries what), Cortex Sense, Business Ontology terms, questions to a semantic view through Cortex Analyst, the refresh history and lag of dynamic tables, warehouse sizing. Hands the task to Cortex Code as a subagent (cortex exec) with the context of this session, then goes on with its answer."
---

# Hand a Snowflake task to Cortex Code

Cortex Code (`cortex`) is Snowflake's coding agent. It knows the account and the Snowflake features that the dltHub
skills only touch. Here it runs as a subagent: you write it a brief with the task and its context, it works with its
own tools and bundled skills, and you go on with its answer in this session.

## 1. Agree on the handover

Tell the user in one or two lines what goes to Cortex Code and why it fits, and wait for a yes. Ask also whether
Cortex Code may write: by default it runs read-only SQL and writes no files. A write in Snowflake (an object, a
comment, a Business Ontology term) needs the user's explicit yes for this task.

Check that the CLI is there: `cortex --version`. Without it, tell the user how to install Cortex Code
(https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli) and go on without the handover.

## 2. Write the brief

Write the brief to a file in the system temp dir, not in the workspace. It holds everything Cortex Code needs,
because it does not see this session:

- **Task**: one paragraph, the outcome you need.
- **Context**: the workspace path; the files to read, for example `.dlthub/ontology/<name>/CDM.dbml`,
  `ontology.md`, `context.md`; the database, schema and tables; what this session found already.
- **Bundled skills**: name the one that fits when you know it, for example `$cortex-sense`, `$business-ontology`,
  `$query-semantic-view`.
- **Limits**: read-only unless the user allowed writes; start every SQL statement with its upper-case keyword
  (`SELECT`, `SHOW`, `DESCRIBE`), which the permission rules match; never read `secrets.toml` files,
  `connections.toml` or key files; write files only where the brief says (`.dlthub/ontology/<name>/`).
- **Answer**: what to return, in markdown sections: findings, the SQL that it ran or proposes, the files it wrote,
  open questions.

## 3. Run it

Use the Snowflake connection of the destination. Ask the user for its name; never read `connections.toml`.

```sh
cortex exec --file <brief> -c <connection> -w <workspace> \
  --allowed "read,skill,sql(SELECT:*),sql(SHOW:*),sql(DESCRIBE:*)" \
  --max-turns 30 --no-history -o <answer file>
```

- `exec` rejects every tool call that `--allowed` does not match. A rule is a tool type (`read`, `write`, `edit`,
  `bash`, `sql`, `skill`, `web_search`, …), alone or with a prefix: `sql(SELECT:*)` allows the SQL statements that
  start with `SELECT ` and nothing else. The prefix is case-sensitive, so the brief says to start every statement
  with the upper-case keyword.
- Read-only is the default above. Add `write` and `edit` only when the brief asks for files (without `edit`, Cortex
  Code cannot fix a file it wrote), and allow every SQL statement
  with `sql` only after the user said yes to writes. Never use `--bypass` without the user's yes.
- When the answer says that a tool was blocked, show the user which one and ask whether to allow it in a second run.
- A long task takes minutes: run it in the background when you can, and tell the user.

## 4. Use the answer

Read the answer file. Check its claims against the files and the account where you can, then show the user a short
summary: what it found, what it changed, the SQL it proposes. Go on with the skill that needed the handover, with
these results. Writes that Cortex Code proposes but did not run go through the user's yes, like any other write.
