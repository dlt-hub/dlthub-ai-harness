# dlthub-router (entry skill) trigger eval

## Cross-agent scope

The `dlthub-router` skill must trigger and route correctly on **all three agents** — Claude Code, Cursor, and Codex. `SKILL.md` is a cross-agent standard, so the skill installs natively to `.claude/skills/`, `.cursor/skills/`, and `.agents/skills/` respectively, and the always-loaded toolkit index ships to each agent's always-loaded surface (rule on Claude/Cursor, `AGENTS.md` on Codex).

**What is validated automatically vs. manually today:**

- **Automated trigger eval (Claude only):** the harness below drives the agent headlessly via `claude -p`. There is no equivalent headless driver wired for Cursor or Codex yet, so automated trigger-rate measurement currently runs on Claude only.
- **Cross-agent install + always-loaded surface (all three):** verified via `dlthub ai toolkit install … --strict` for `--agent claude|cursor|codex` and by inspecting the generated rule / `.mdc` / `AGENTS.md` (the index reaches the always-loaded surface on each).
- **Cursor/Codex trigger automation is a follow-up** — needs headless runners for those agents. Until then, trigger behavior on Cursor/Codex is checked manually.

## Status: eval framework bug — skill triggers correctly

### The bug

`run_eval.py` creates a **command** in `.claude/commands/` as a proxy for the skill, then checks if the agent reads that command. But when the real skill exists in the agent's skills dir, the agent invokes the **skill** via the `Skill` tool (not the proxy command). The eval detection misses this because it looks for the command name, not the skill name.

### Proof: `claude -p` triggers the skill

Running `claude -p "how can I build my first pipeline?"` from a clean eval workspace:

1. First action: `Skill(dlthub-router)` — correct trigger
2. The skill routes from the always-loaded toolkit index (no MCP round-trip needed); falls back to `list_toolkits` only for needs not in the index
3. Installs `rest-api-pipeline` and hands over to its entry skill (`find-source`) **in the same session** (no restart)

### How to test (Claude, automated)

```bash
# Create clean workspace
uv run python tools/create_eval_workspace.py evals/init/dlthub-router

# Run claude -p from it
cd evals/.evals/init--dlthub-router--init-only
CLAUDECODE= claude -p "how can I build my first pipeline?" --output-format stream-json
```

Check the stream for `{"name":"Skill","input":{"skill":"dlthub-router"}}`.

### How to check (Cursor / Codex, manual until runners exist)

Create the workspace for the target agent and open it in that agent, then issue the same prompts and confirm the skill triggers and routes:

```bash
# (agent param support tracked as follow-up; today the workspace installs for --agent claude)
```

### Negative cases (100% precision in automated eval)

All 10 should-not-trigger queries correctly did NOT trigger in `run_eval.py` (0/3 trigger rate each). The description's negative guard works.
