"""Pseudonymize a captured inspector run before it is committed as a test fixture.

A capture is a verbatim copy of what one evaluation read from a live workspace: run
records, run logs, the stored result and trace, job run lists, pipeline traces. This
repository is public, so every identifier that ties a capture to real infrastructure is
replaced before the files land in git.

Replacement is a keyed hash of the original value, so a given identifier maps to the same
pseudonym in every file and the cross-references inside a capture still resolve. The key is
fixed in this file: the mapping is reproducible, and the captures are safe because the
source workspace is synthetic. The hash output is not reversible without the original value,
but a committed key still allows confirmation by guessing likely inputs.

What is replaced:

- run, pipeline-run and trace UUIDs, leaving a hand-written placeholder alone
- pipeline transaction ids (32 hex characters)
- dlt load ids, both the `<epoch>.<fraction>` form and the bare epoch in a load path
- the runner's temporary directory, `/tmp/dlt_run_<suffix>`
- any literal pair listed in the substitution file, for names no pattern can find: a cloud
  project, a workspace logger name, a model deployment

The substitution file holds the real names, so it stays out of the repository. It is JSON,
`{"<original>": "<pseudonym>"}`, and defaults to `.context/scrub-literals.json`. Without it
only the structural passes run, and `--verify` cannot confirm the literals are gone.

Timestamps, job names, dataset names, table names and the quoted error text are kept. They
come from a demo workspace with synthetic sources, they carry no account or credential, and
the checks under test read them.

usage: uv run python tools/scrub_capture.py [--literals <path>] <capture directory> [...]
       uv run python tools/scrub_capture.py --verify [--literals <path>] <directory> [...]
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

KEY = b"dlthub-ai-harness/job-inspector-eval/fixture-pseudonym/v1"
LITERALS_DEFAULT = ".context/scrub-literals.json"

MARK = "0000"
"""Every pseudonym carries this, so `--verify` can tell a scrubbed capture from a raw one
without holding the originals. A real identifier wears it with probability 2**-16."""

EPOCH_FLOOR, EPOCH_RANGE = 1_600_000_000, 31_000_000
"""Pseudonymous load ids sit in late 2020. A real one is the instant the load ran."""

UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")

HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
LOAD_ID = re.compile(r"\b(1[6-9][0-9]{8})(\.[0-9]{1,9})?\b")
RUN_DIR = re.compile(r"(?<=/tmp/dlt_run_)[a-z0-9]{6,12}\b")


def placeholder(value: str) -> bool:
    """A uuid a test wrote by hand, `11111111-1111-4111-8111-111111111111` and its kind.

    Every character outside the version and variant nibbles is the same one, which no
    generated id is. Such an id names nothing real and the tests match on it verbatim.
    """
    digits = value.replace("-", "")
    rest = digits[:12] + digits[13:16] + digits[17:]
    return len(digits) == 32 and len(set(rest)) == 1


def _digest(value: str, label: str) -> str:
    return hmac.new(KEY, f"{label}:{value}".encode(), hashlib.sha256).hexdigest()


def _uuid(value: str) -> str:
    h = _digest(value, "uuid")
    # the version and variant nibbles keep it reading as a v4 uuid; the node carries MARK
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{MARK}{h[20:28]}"


def _hex32(value: str) -> str:
    return MARK + _digest(value, "hex32")[:28]


def _epoch(value: str) -> str:
    return str(EPOCH_FLOOR + int(_digest(value, "epoch")[:6], 16) % EPOCH_RANGE)


def _fraction(value: str) -> str:
    return "." + _digest(value, "fraction")[:6].translate(str.maketrans("abcdef", "012345"))


def _run_dir(value: str) -> str:
    return _digest(value, "rundir")[:8]


def scrub(text: str, literals: dict[str, str]) -> str:
    """Replace every identifier class in `text`, the same way in every file."""
    for original, replacement in literals.items():
        text = text.replace(original, replacement)
    text = RUN_DIR.sub(lambda m: _run_dir(m.group(0)), text)
    # uuids and transaction ids first: a load id cannot be read out of a hyphenated id, but
    # rewriting one would hide the id from the passes below
    text = UUID.sub(lambda m: m.group(0) if placeholder(m.group(0)) else _uuid(m.group(0)), text)
    text = HEX32.sub(lambda m: _hex32(m.group(0)), text)
    text = LOAD_ID.sub(
        lambda m: _epoch(m.group(1)) + (_fraction(m.group(2)) if m.group(2) else ""), text
    )
    return text


def residuals(text: str, literals: dict[str, str] | None = None) -> list[str]:
    """Every identifier in `text` that is not a pseudonym this module produced.

    The structural passes are checked by the mark each pseudonym carries, so this holds a
    scrubbed capture to account without the originals. Pass `literals` as well when the
    substitution file is at hand, to catch a name no pattern finds.
    """
    found = [literal for literal in literals or {} if literal in text]
    found += [m for m in UUID.findall(text) if not m.startswith(MARK, 24) and not placeholder(m)]
    found += [m for m in HEX32.findall(text) if not m.startswith(MARK)]
    found += [
        m for m in LOAD_ID.findall(text) if not EPOCH_FLOOR <= int(m[0]) < EPOCH_FLOOR + EPOCH_RANGE
    ]
    found += [
        m
        for m in re.findall(r"/tmp/dlt_run_[a-z0-9]+", text)
        if not re.fullmatch(r"/tmp/dlt_run_[0-9a-f]{8}", m)
    ]
    return [str(item) for item in found]


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        return None


def _files(targets: list[str]) -> list[Path]:
    """Every text file under the targets. A capture holds JSON; a transcript is a log."""
    present = [Path(target) for target in targets if Path(target).is_dir()]
    found = sorted(path for root in present for path in root.rglob("*") if path.is_file())
    return [path for path in found if _text(path) is not None]


def _literals(path: str) -> dict[str, str]:
    file = Path(path)
    if not file.exists():
        if path != LITERALS_DEFAULT:
            raise SystemExit(f"no substitution file at {path}")
        print(f"note: no {LITERALS_DEFAULT}, running the structural passes only")
        return {}
    return json.loads(file.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    verify = "--verify" in argv
    argv = [arg for arg in argv if arg != "--verify"]
    substitutions = LITERALS_DEFAULT
    if "--literals" in argv:
        at = argv.index("--literals")
        substitutions = argv[at + 1]
        argv = argv[:at] + argv[at + 2 :]
    targets = argv
    if not targets:
        print(__doc__)
        return 2
    literals = _literals(substitutions)
    failed = False
    for path in _files(targets):
        text = _text(path) or ""
        if verify:
            found = residuals(text, literals)
            if found:
                failed = True
                print(f"FAIL {path}: {sorted(set(found))}")
            continue
        if not residuals(text, literals) and not residuals(path.stem):
            continue  # already scrubbed: every identifier in it carries the mark
        scrubbed = scrub(text, literals)
        if scrubbed != text:
            path.write_text(scrubbed, encoding="utf-8")
            print(f"scrubbed {path}")
        # a capture names its files after the ids inside them, so the stem moves too
        renamed = scrub(path.stem, literals)
        if renamed != path.stem:
            path.rename(path.with_name(renamed + path.suffix))
            print(f"renamed  {path.name} -> {renamed}{path.suffix}")
    if verify and not failed:
        print(f"clean: {len(_files(targets))} files")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
