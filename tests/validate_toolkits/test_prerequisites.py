"""Every public SKILL.md carries the prerequisites template right after its first heading."""

from pathlib import Path

from tests.validate_toolkits.utils import write

from tools import validate_toolkits as V

TEMPLATE = "Prerequisites: install dlt.\n"


def prerequisites_root(tmp_path: Path, block: str) -> Path:
    write(tmp_path / V._PREREQUISITES_TEMPLATE, TEMPLATE)
    toolkit = V._PREREQUISITES_TOOLKITS[0]
    skill = tmp_path / V.AI_DIR / toolkit / "skills" / "s" / "SKILL.md"
    write(skill, f"---\nname: s\ndescription: d\n---\n\n# S\n\n{block}\nBody.\n")
    return tmp_path


def test_a_skill_with_the_template_verbatim_passes(tmp_path: Path) -> None:
    assert V.validate_prerequisites(prerequisites_root(tmp_path, TEMPLATE)) == []


def test_a_skill_whose_block_differs_is_an_error(tmp_path: Path) -> None:
    errors = V.validate_prerequisites(prerequisites_root(tmp_path, "Prerequisites: other.\n"))

    assert len(errors) == 1
    assert "differs from" in errors[0]
