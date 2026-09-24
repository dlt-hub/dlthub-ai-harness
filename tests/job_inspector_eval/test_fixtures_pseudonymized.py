"""The committed captures carry no identifier from the workspace they were taken on.

A capture is a verbatim copy of what one evaluation read from a live workspace, and this
repository is public, so `tools/scrub_capture.py` rewrites every identifier before the files
land in git. Each pseudonym it writes carries a mark, which is what these tests read: they
hold the fixtures to account without the originals, which stay out of the repository.
"""

import importlib.util
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRUBBER = Path(__file__).resolve().parents[2] / "tools" / "scrub_capture.py"

spec = importlib.util.spec_from_file_location("scrub_capture", SCRUBBER)
scrub_capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scrub_capture)

FILES = [path for path in sorted(FIXTURES.rglob("*")) if path.is_file()]


def test_the_captures_are_present():
    assert FILES, f"no fixture under {FIXTURES}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(FIXTURES)))
def test_a_fixture_holds_no_unscrubbed_identifier(path):
    found = scrub_capture.residuals(path.read_text())
    assert found == [], f"{path.relative_to(FIXTURES)} carries {sorted(set(found))}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(FIXTURES)))
def test_a_fixture_is_named_after_a_scrubbed_id(path):
    assert scrub_capture.residuals(path.stem) == []


def test_the_scrubber_ships_no_original():
    """The names no pattern finds live in the substitution file, which is not committed."""
    source = SCRUBBER.read_text()
    assert scrub_capture.LITERALS_DEFAULT.startswith(".context/")
    assert '"' + scrub_capture.LITERALS_DEFAULT + '"' in source
    assert "LITERALS = {" not in source


def test_a_hand_written_placeholder_survives_the_scrubber():
    """`11111111-...` and its kind name nothing, and the tests match on them verbatim."""
    written = "11111111-1111-4111-8111-111111111111"
    assert scrub_capture.scrub(written, {}) == written
    assert scrub_capture.residuals(written) == []
    generated = "7f3a91c4-2b6d-4e18-9a05-c1d8e2f40b73"
    assert scrub_capture.scrub(generated, {}) != generated
    assert scrub_capture.residuals(generated) == [generated]
