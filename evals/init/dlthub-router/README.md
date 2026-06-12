# dlthub-router (entry skill) trigger eval

## Status: eval framework bug — skill triggers correctly

### The bug

`run_eval.py` creates a **command** in `.claude/commands/` as a proxy for the skill, then checks if Claude reads that command. But when the real skill exists in `.claude/skills/`, Claude invokes the **skill** via the `Skill` tool (not the proxy command). The eval detection misses this because it looks for the command name, not the skill name.

### Proof: `claude -p` triggers the skill

Running `claude -p "how can I build my first pipeline?"` from a clean eval workspace:

1. Claude's first action: `Skill(dlthub-router)` — correct trigger
2. The skill routes from the always-loaded toolkit index (no MCP round-trip needed); falls back to `list_toolkits` only for needs not in the index
3. Installs `rest-api-pipeline` and hands over to its entry skill (`find-source`)

### How to test

```bash
# Create clean workspace
uv run python tools/create_eval_workspace.py evals/init/dlthub-router

# Run claude -p from it
cd evals/.evals/init--dlthub-router--init-only
CLAUDECODE= claude -p "how can I build my first pipeline?" --output-format stream-json
```

Check the stream for `{"name":"Skill","input":{"skill":"dlthub-router"}}`.

### Negative cases (100% precision in automated eval)

All 10 should-not-trigger queries correctly did NOT trigger in `run_eval.py` (0/3 trigger rate each). The description's negative guard works.
