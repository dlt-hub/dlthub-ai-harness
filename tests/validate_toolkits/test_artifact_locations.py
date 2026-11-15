"""Toolkits write artifacts only to the artifact locations of a workspace, all under `.dlthub/`.

A platform folder (`.dlthub/snowflake/`, `.dlthub/platform/`) belongs to one platform toolkit, and the
locations that the harness retired must not come back.
"""

from pathlib import Path

import pytest

from tests.utils import REPO_ROOT
from tests.validate_toolkits.utils import toolkit

from tools import validate_toolkits as V


def location_errors(root: Path) -> list[str]:
    errors: list[str] = []
    V.validate_artifact_locations(root, V.build_component_inventory(root), errors)
    return errors


def test_shipped_toolkits_use_artifact_locations() -> None:
    assert location_errors(REPO_ROOT) == []


@pytest.mark.parametrize(
    "body",
    [
        "write `.dlthub/ontology/<cdm-name>/taxonomy.json`",
        "set `import_schema_path=\".dlthub/schemas\"`",
        "export to `.dlthub/schemas/export/` when the user wants it committed",
        "save the plan to `.dlthub/explorations/<pipeline_name>/analysis_plan.md`",
        "a platform toolkit owns `.dlthub/<platform>/`",
        "the `.dlthub/` folder",
    ],
)
def test_standard_locations_pass(tmp_path: Path, body: str) -> None:
    toolkit(tmp_path, "transformations", skills=("annotate-sources",), skill_body=body + "\n")

    assert location_errors(tmp_path) == []


@pytest.mark.parametrize(
    "body,reason",
    [
        ("write `.dlthub/models/cdm.dbml`", "not an artifact location"),
        ("write `.schema/<cdm>/taxonomy.json`", "retired location `.schema/`"),
        ('import_schema_path="schemas/import"', "retired location `schemas/import|export`"),
        ("the view in `.dlthub/ontology/snowflake/x_sv.sql`", "retired location `.dlthub/ontology/snowflake`"),
        ("write `tools/get_github_schema.py`", "throwaway script"),
    ],
)
def test_other_locations_fail(tmp_path: Path, body: str, reason: str) -> None:
    toolkit(tmp_path, "transformations", skills=("annotate-sources",), skill_body=body + "\n")

    errors = location_errors(tmp_path)

    assert any(reason in e for e in errors), errors


def test_platform_folder_belongs_to_its_toolkit(tmp_path: Path) -> None:
    body = "deploy records are in `.dlthub/snowflake/deploy/<environment>/`\n"
    toolkit(tmp_path, "snowflake-platform", skills=("deploy-snowflake-workspace",), skill_body=body)
    toolkit(tmp_path, "dlthub-platform", skills=("deploy-workspace",), skill_body=body)

    errors = location_errors(tmp_path)

    assert len(errors) == 1
    assert "[dlthub-platform]" in errors[0] and "belongs to snowflake-platform" in errors[0]
