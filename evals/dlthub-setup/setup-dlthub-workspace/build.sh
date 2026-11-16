#!/usr/bin/env bash
# Build the eval workspaces by hand, since create_eval_workspace.py always runs dlthub ai init.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
skill="$root/workbench/dlthub-setup/skills/setup-dlthub-workspace"
out="$root/evals/.evals"
rm -rf "$out/dlthub-setup--setup-dlthub-workspace--bare" "$out/dlthub-setup--setup-dlthub-workspace--data-project"
mkdir -p "$out/dlthub-setup--setup-dlthub-workspace--bare/.claude/skills"
cp -R "$skill" "$out/dlthub-setup--setup-dlthub-workspace--bare/.claude/skills/"
cp -R "$here/fixtures/data-project" "$out/dlthub-setup--setup-dlthub-workspace--data-project"
cp -R "$skill" "$out/dlthub-setup--setup-dlthub-workspace--data-project/.claude/skills/"
echo "built bare and data-project in $out"

# Workspaces where dltHub is already set up, plus the dlthub-setup skill from the marketplace.
for spec in "with-init:" "with-rest-api:rest-api-pipeline"; do
  ws="$out/dlthub-setup--setup-dlthub-workspace--${spec%%:*}"
  (cd "$root" && uv run python -c "
import sys; sys.path.insert(0, 'tools')
from pathlib import Path
from create_eval_workspace import create_single_workspace, get_dlt_version
tk = [t for t in sys.argv[2].split(',') if t]
create_single_workspace(Path(sys.argv[1]), f'dlt[hub]=={get_dlt_version()}', tk)
" "$ws" "${spec#*:}") > /dev/null
  cp -R "$skill" "$ws/.claude/skills/"
  echo "built ${spec%%:*}: $(ls "$ws/.claude/skills" | tr '\n' ' ')"
done
