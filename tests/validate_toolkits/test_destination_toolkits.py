"""Destination toolkits are pluggable too: the router reaches them through one row and reacts to the
name of each destination, only a platform toolkit depends on one, and a generic toolkit names none.

A destination toolkit starts its description with `Destination toolkit (<destination>):`. Generic
toolkits ask for "the destination toolkit" of a destination at their hook points.
"""

from pathlib import Path

import pytest

from tests.utils import REPO_ROOT
from tests.validate_toolkits.utils import fake_root, toolkit

from tools import validate_toolkits as V

DESTINATION = f"{V.DESTINATION_LABEL} (Snowflake): connect to Snowflake and load into it."
PLATFORM = f"{V.PLATFORM_LABEL} (Snowflake): deploy to Snowflake."


def index_errors(root: Path, names: set[str]) -> list[str]:
    errors: list[str] = []
    V.validate_index_drift(root, names, V.build_component_inventory(root), errors)
    return errors


def agnostic_errors(root: Path) -> list[str]:
    errors: list[str] = []
    V.validate_destination_agnostic(root, V.build_component_inventory(root), errors)
    return errors


def test_shipped_destination_toolkits_are_pluggable() -> None:
    inventory = V.build_component_inventory(REPO_ROOT)

    assert inventory["destination-snowflake"]["destination"]
    assert inventory["destination-snowflake"]["destination_name"] == "Snowflake"
    assert agnostic_errors(REPO_ROOT) == []


def test_index_skips_destination_toolkits(tmp_path: Path) -> None:
    root = fake_root(tmp_path, ["rest-api-pipeline"])
    toolkit(root, "rest-api-pipeline")
    toolkit(root, "destination-snowflake", description=DESTINATION)

    assert index_errors(root, {"rest-api-pipeline", "destination-snowflake"}) == []


def test_index_names_a_destination_toolkit(tmp_path: Path) -> None:
    root = fake_root(tmp_path, ["destination-snowflake"])
    toolkit(root, "destination-snowflake", description=DESTINATION)

    errors = index_errors(root, {"destination-snowflake"})

    assert len(errors) == 1 and "which is a destination toolkit" in errors[0]


def test_index_without_the_destination_row(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [], destination_row=False)
    toolkit(root, "destination-snowflake", description=DESTINATION)

    errors = index_errors(root, {"destination-snowflake"})

    assert len(errors) == 1 and "a destination toolkit" in errors[0]


def test_router_does_not_name_the_destination(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [], router_description="Use when the user wants to load data.")
    toolkit(root, "destination-snowflake", description=DESTINATION)

    errors = index_errors(root, {"destination-snowflake"})

    assert len(errors) == 1 and "does not name 'Snowflake'" in errors[0]


def test_destination_label_without_a_destination(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [])
    toolkit(root, "destination-snowflake", description=f"{V.DESTINATION_LABEL}: load data.")

    errors = index_errors(root, {"destination-snowflake"})

    assert len(errors) == 1 and "(<destination>):" in errors[0]


def test_generic_toolkit_depends_on_a_destination_toolkit(tmp_path: Path) -> None:
    toolkit(tmp_path, "transformations", dependencies=("destination-snowflake",))
    toolkit(tmp_path, "destination-snowflake", description=DESTINATION)

    errors = agnostic_errors(tmp_path)

    assert len(errors) == 1 and "depends on 'destination-snowflake'" in errors[0]


@pytest.mark.parametrize(
    "body",
    ["install **destination-snowflake**", "then run (`create-snowflake-dynamic-tables`)"],
)
def test_generic_toolkit_names_the_destination_toolkit(tmp_path: Path, body: str) -> None:
    toolkit(tmp_path, "transformations", skills=("create-transformation",), skill_body=body + "\n")
    toolkit(
        tmp_path,
        "destination-snowflake",
        skills=("create-snowflake-dynamic-tables",),
        description=DESTINATION,
    )

    errors = agnostic_errors(tmp_path)

    assert len(errors) == 1 and "destination toolkit 'destination-snowflake'" in errors[0]
    assert "SKILL.md:5" in errors[0]


def test_generic_toolkit_may_ask_for_the_destination_toolkit(tmp_path: Path) -> None:
    body = "When the destination has a destination toolkit, offer it. Snowflake works too.\n"
    toolkit(tmp_path, "transformations", skills=("create-transformation",), skill_body=body)
    toolkit(tmp_path, "destination-snowflake", description=DESTINATION)

    assert agnostic_errors(tmp_path) == []


def test_platform_toolkit_depends_on_and_names_its_destination_toolkit(tmp_path: Path) -> None:
    toolkit(
        tmp_path,
        "snowflake-platform",
        skills=("deploy-snowflake-workspace",),
        dependencies=("destination-snowflake",),
        description=PLATFORM,
        skill_body="credentials: (`setup-snowflake-destination`) of **destination-snowflake**\n",
    )
    toolkit(
        tmp_path,
        "destination-snowflake",
        skills=("setup-snowflake-destination",),
        description=DESTINATION,
    )

    assert agnostic_errors(tmp_path) == []


def test_label_in_plugin_and_marketplace() -> None:
    """The shipped destination toolkit carries the label in both descriptions."""
    errors, _, _ = V.validate(REPO_ROOT, "destination-snowflake")

    assert not [e for e in errors if V.DESTINATION_LABEL in e]
