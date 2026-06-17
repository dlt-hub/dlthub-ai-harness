# toolkit-dispatch trigger eval

## Status: eval framework bug — skill triggers correctly

### The bug

`run_eval.py` creates a **command** in `.claude/commands/` as a proxy for the skill, then checks if Claude reads that command. But when the real skill exists in `.claude/skills/`, Claude invokes the **skill** via the `Skill` tool (not the proxy command). The eval detection misses this because it looks for the command name, not the skill name.

### Proof: `claude -p` triggers the skill

Running `claude -p "how can I build my first pipeline?"` from a clean eval workspace:

1. Claude's first action: `Skill(toolkit-dispatch)` — correct trigger
2. Skill loads, calls `list_toolkits` MCP tool
3. Calls `toolkit_info("rest-api-pipeline")` for details
4. Recommends installing `rest-api-pipeline`, asks user what API they want

### How to test

```bash
# Create clean workspace
uv run python tools/create_eval_workspace.py --name test-dispatch

# Run claude -p from it
cd evals/.evals/test-dispatch
CLAUDECODE= claude -p "how can I build my first pipeline?" --output-format stream-json
```

Check the stream for `{"name":"Skill","input":{"skill":"toolkit-dispatch"}}`.

### Negative cases (100% precision in automated eval)

All 10 should-not-trigger queries correctly did NOT trigger in `run_eval.py` (0/3 trigger rate each). The description's negative guard works.
