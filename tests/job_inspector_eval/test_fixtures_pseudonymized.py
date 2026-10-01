"""No committed file carries an identifier from the workspace it was taken on.

This repository is public, so `tools/scrub_capture.py` rewrites every identifier before a
capture lands in git and marks each pseudonym it writes. These tests read the mark, so they
check the committed tree without the originals, which stay out of the repository.

The fixtures are swept file by file. Every other tracked file is swept together, because a raw
id pasted into a test module is as public as one left in a capture.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRUBBER = REPO / "tools" / "scrub_capture.py"

spec = importlib.util.spec_from_file_location("scrub_capture", SCRUBBER)
scrub_capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scrub_capture)

FILES = [path for path in sorted(FIXTURES.rglob("*")) if path.is_file()]

# the raw inputs that prove the scrubber rewrites them, and a run dir too short to carry a
# pseudonym. a registry rather than a constant: naming a value here would plant it in this file
# and the sweep would report it. entries are exact, so a new identifier in those files still fails.
REGISTRY = Path(__file__).resolve().parent / "allowed_identifiers.json"
ALLOWED = {name: set(values) for name, values in json.loads(REGISTRY.read_text()).items()}


def _tracked() -> list[Path]:
    listing = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO / name for name in listing.split("\0") if name]


def test_the_captures_are_present():
    assert FILES, f"no fixture under {FIXTURES}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(FIXTURES)))
def test_a_fixture_holds_no_unscrubbed_identifier(path):
    found = scrub_capture.residuals(path.read_text())
    assert found == [], f"{path.relative_to(FIXTURES)} carries {sorted(set(found))}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(FIXTURES)))
def test_a_fixture_is_named_after_a_scrubbed_id(path):
    assert scrub_capture.residuals(path.stem) == []


def test_no_other_tracked_file_holds_an_unscrubbed_identifier():
    """The sweep above reads the fixtures only, so an id pasted into a module went unseen."""
    offenders = {}
    for path in _tracked():
        if FIXTURES in path.parents or path == REGISTRY or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        name = path.relative_to(REPO).as_posix()
        found = set(scrub_capture.residuals(text)) - ALLOWED.get(name, set())
        if found:
            offenders[name] = sorted(found)
    assert offenders == {}, f"unscrubbed identifiers: {offenders}"


@pytest.mark.parametrize("name", sorted(ALLOWED), ids=lambda n: n.rsplit("/", 1)[1])
def test_an_allowed_identifier_is_still_in_the_file_that_claims_it(name):
    """A stale entry would widen the sweep without anything saying so."""
    found = set(scrub_capture.residuals((REPO / name).read_text(encoding="utf-8")))
    assert ALLOWED[name] <= found, f"{name} no longer carries {sorted(ALLOWED[name] - found)}"


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


def test_a_scrubbed_load_id_is_still_in_the_load_id_match_band():
    """`--verify` must recognize every load id the scrubber writes."""
    raw = "load_id=1695312345.123456"
    scrubbed = scrub_capture.scrub(raw, {})
    assert scrubbed != raw
    assert scrubbed.startswith("load_id=16")
    assert scrub_capture.residuals(scrubbed) == []
