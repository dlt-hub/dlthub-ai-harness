"""Fixtures that run the toolkit's agents on dlt's pydantic-ai loop with an offline model.

Everything but the model (`TestModel`, no MCP server) is what a deployment uses.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest
from pydantic_ai.models.test import TestModel

from dlt.common.configuration.container import Container
from dlt.common.configuration.plugins import PluginContext, hookimpl
from dlt.common.configuration.specs.pluggable_run_context import PluggableRunContext
from dlt.common.runtime.run_context import switch_context
from dlt._workspace.deployment.agent.loops.pydantic_ai import PydanticAILoop

from tests.utils import REPO_ROOT

NULL_LOOP = "null-pydantic-ai"
PLUGIN_NAME = "null_model_loop"


class NullModelLoop(PydanticAILoop):
    """dlt's pydantic-ai loop answered by `TestModel`, with no MCP server."""

    LOOP_TYPE = NULL_LOOP
    output: Optional[Dict[str, Any]] = None
    """What the model answers; `None` lets `TestModel` generate it from the output schema."""

    def _build_model(self) -> Any:
        return TestModel(call_tools=[], custom_output_args=NullModelLoop.output)

    def _build_toolsets(self) -> List[Any]:
        return []


class NullModelLoopPlugin:
    @hookimpl(specname="plug_agent_loop")
    def plug_agent_loop(self, loop_type: str) -> Any:
        return NullModelLoop if loop_type == NULL_LOOP else None


@pytest.fixture(scope="session")
def installed_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A workspace with the `dlthub-platform` toolkit installed from this repo, once."""
    root = tmp_path_factory.mktemp("installed_workspace")
    (root / ".dlt").mkdir()
    (root / ".dlt" / ".workspace").touch()
    dlthub = Path(sys.executable).parent / "dlthub"
    subprocess.run(
        [str(dlthub), "--non-interactive", "ai", "toolkit", "install", "dlthub-platform",
         "--location", str(REPO_ROOT), "--agent", "claude"],
        cwd=root, check=True, capture_output=True,
    )
    return root


@pytest.fixture
def workspace(
    installed_workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """A fresh copy of the installed workspace, active, on the null-model loop."""
    run_dir = tmp_path / "workspace"
    shutil.copytree(installed_workspace, run_dir)
    monkeypatch.chdir(run_dir)
    monkeypatch.setenv("AGENT__LOOP", NULL_LOOP)
    ctx = switch_context(str(run_dir), required="WorkspaceRunContext")
    # an empty ~/.dlt: no platform token, so the run looks nothing up on the platform
    if hasattr(ctx, "_global_dir"):
        ctx._global_dir = str(tmp_path / "global")
        os.makedirs(ctx._global_dir, exist_ok=True)
        Container()[PluggableRunContext].reload_providers()

    manager = Container()[PluginContext].manager
    if manager.get_plugin(PLUGIN_NAME) is None:
        manager.register(NullModelLoopPlugin(), name=PLUGIN_NAME)
    NullModelLoop.output = None
    yield run_dir


@pytest.fixture
def null_loop() -> type:
    """The loop the `workspace` runs agents on; set `output` to fix the answer."""
    return NullModelLoop
