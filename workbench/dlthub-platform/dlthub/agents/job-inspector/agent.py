"""Hooks for the job-inspector agent job: `validate_output` links run ids and job refs in the
summary."""

from typing import Any, Dict

from .links import link_summary


def validate_output(output: Dict[str, Any]) -> Dict[str, Any]:
    return link_summary(output)
