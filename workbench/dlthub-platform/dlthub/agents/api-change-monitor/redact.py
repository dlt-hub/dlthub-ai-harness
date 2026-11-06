"""Mask credential literals in workspace text before it reaches a prompt or a report.

The agent quotes code lines in its prompt, its findings and the result it stores on the
platform, so a key hard-coded in a pipeline would travel with them. Values assigned to
credential-like names and strings shaped like known tokens are replaced by `***`.
"""

from __future__ import annotations

import re

MASK = "***"

_ASSIGNED = re.compile(
    r"""(?ix)
    ((?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token|secret|
       client[_-]?secret|password|passwd|private[_-]?key|developer[_-]?token)
     ["']?\s*[:=]\s*f?["'])
    ([^"'{}\s]{6,})
    (["'])
    """
)
# in a string literal the value after the scheme is a header, so it is always masked
_QUOTED_BEARER = re.compile(r"""(?i)(["'](?:bearer|basic))\s+[^"'\s]{8,}(?=["'])""")
# in prose only a value with a digit is a token, so `basic authentication` stays
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+(?=[A-Za-z._~+/=-]*\d)[A-Za-z0-9._~+/=-]{12,}")
_SHAPED = re.compile(
    r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{8,}"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}"
    r"|\bxox[abprs]-[A-Za-z0-9-]{10,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\bAIza[0-9A-Za-z_-]{30,}"
    r"|\bdlt_(?:u|sa)_[A-Za-z0-9]{8,}"
    r"|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"
)
# a long unnamed key: letters and digits mixed, no underscore as field names carry
_OPAQUE = re.compile(r"(?<![\w/.-])(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{32,}(?![\w/.-])")


def redact(text: str) -> str:
    """The text with every credential-shaped literal replaced by `***`."""
    text = _ASSIGNED.sub(lambda m: f"{m.group(1)}{MASK}{m.group(3)}", text)
    text = _QUOTED_BEARER.sub(lambda m: f"{m.group(1)} {MASK}", text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} {MASK}", text)
    text = _SHAPED.sub(MASK, text)
    return _OPAQUE.sub(MASK, text)
