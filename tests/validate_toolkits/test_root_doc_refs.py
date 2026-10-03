"""A toolkit file may not point at a document in the repo root.

`dlthub ai toolkit install` copies the toolkit directory and nothing above it, so a workspace
that follows such a reference finds no file. The document's URL is the way to cite one.
"""

from pathlib import Path

from fakes import REPO_ROOT, fake_root, toolkit, write

import validate_toolkits as V


def root_doc_errors(root: Path, name: str) -> list[str]:
    errors: list[str] = []
    V.validate_toolkit_content(
        name,
        root / V.AI_DIR / name,
        {name},
        V.build_component_inventory(root),
        errors,
        warnings=[],
    )
    return [e for e in errors if "repo root" in e]


def test_the_shipped_toolkits_name_no_root_document() -> None:
    for name in sorted(p.name for p in (REPO_ROOT / V.AI_DIR).iterdir() if p.is_dir()):
        assert root_doc_errors(REPO_ROOT, name) == [], name


def test_a_rule_naming_a_root_document_is_an_error(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [])
    toolkit(root, "dlthub-platform", skills=("deploy-workspace",))
    write(root / "SPEC.md", "a document at the repo root\n")
    rule = root / V.AI_DIR / "dlthub-platform" / "rules" / "workflow.md"
    write(rule, rule.read_text() + "\nSee `SPEC.md` for the snippets.\n")

    errors = root_doc_errors(root, "dlthub-platform")

    assert len(errors) == 1
    assert "workflow.md" in errors[0] and "SPEC.md" in errors[0]


def test_the_same_document_as_a_url_is_fine(tmp_path: Path) -> None:
    """A URL resolves from a workspace, which is the point of the rule."""
    root = fake_root(tmp_path, [])
    toolkit(root, "dlthub-platform", skills=("deploy-workspace",))
    write(root / "SPEC.md", "a document at the repo root\n")
    skill = root / V.AI_DIR / "dlthub-platform" / "skills" / "deploy-workspace" / "SKILL.md"
    write(
        skill,
        skill.read_text()
        + "\nSee https://github.com/dlt-hub/dlthub-ai-harness/blob/master/SPEC.md\n",
    )

    assert root_doc_errors(root, "dlthub-platform") == []


def test_a_markdown_link_to_the_url_keeps_its_text(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [])
    toolkit(root, "dlthub-platform", skills=("deploy-workspace",))
    write(root / "SPEC.md", "a document at the repo root\n")
    skill = root / V.AI_DIR / "dlthub-platform" / "skills" / "deploy-workspace" / "SKILL.md"
    url = "https://github.com/dlt-hub/dlthub-ai-harness/blob/master/SPEC.md"
    write(skill, skill.read_text() + f"\nSee [SPEC.md]({url}).\n")

    assert root_doc_errors(root, "dlthub-platform") == []


def test_a_generic_project_document_is_left_alone(tmp_path: Path) -> None:
    """A skill telling a user to write a README means the user's project, not this repo."""
    root = fake_root(tmp_path, [])
    toolkit(root, "dlthub-platform", skills=("deploy-workspace",))
    write(root / "README.md", "the repo\n")
    skill = root / V.AI_DIR / "dlthub-platform" / "skills" / "deploy-workspace" / "SKILL.md"
    write(skill, skill.read_text() + "\nAdd a README.md to the workspace.\n")

    assert root_doc_errors(root, "dlthub-platform") == []
