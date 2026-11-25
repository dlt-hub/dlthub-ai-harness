"""Find the release notes of an API no source is known for, from its host alone.

Providers publish changelogs at a few common places on their own domain. The hook tries
those before the model is asked to search, and keeps the first page that reads as dated
release notes, so an API missing from the registry still works on a model without web
tools.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Callable, List, Optional

from . import release_notes

# a first label that names the API server rather than the provider
_SERVER_LABELS = {"api", "apis", "rest", "www", "*", "app", "gateway", "graphql"}
_SITES = ["{base}", "developer.{base}", "developers.{base}", "docs.{base}"]
_PATHS = ["/changelog", "/changelog.rss", "/release-notes", "/docs/changelog", "/api/changelog"]
TIMEOUT = 6
MAX_CANDIDATES = 16


def provider_domain(host: str) -> str:
    """The provider's own domain behind an API host, as `acme.io` for `api.acme.io`."""
    labels = [label for label in host.lower().split(".") if label]
    while len(labels) > 2 and (labels[0] in _SERVER_LABELS or labels[0].startswith("api")):
        labels = labels[1:]
    return ".".join(labels)


def candidates(host: str) -> List[str]:
    """Release note urls to try for an API host, the most common places first."""
    base = provider_domain(host)
    urls = [f"https://{site.format(base=base)}{path}" for path in _PATHS for site in _SITES]
    if host.strip("*.") != base:
        urls.append(f"https://{host.strip('*.')}/changelog")
    return urls[:MAX_CANDIDATES]


def fetch_quick(url: str) -> str:
    """The body of `url`, with a short timeout and no retries, raising on an error."""
    import requests

    response = requests.get(url, timeout=TIMEOUT, headers={"Accept-Language": "en-US,en"})
    response.raise_for_status()
    if "charset" not in response.headers.get("content-type", "").lower():
        response.encoding = "utf-8"
    return str(response.text)


def find_source(
    name: str, hosts: List[str], today: date, fetch: Callable[[str], str] = fetch_quick
) -> Optional[str]:
    """The first candidate url that parses into dated release notes, or None."""
    urls = [url for host in sorted(hosts) for url in candidates(host)]
    urls = list(dict.fromkeys(urls))

    def dated(url: str) -> bool:
        try:
            notes = release_notes.parse(name, url, fetch(url), date.min, today)
        except Exception:  # a missing page or one that is no changelog is just a miss
            return False
        return any(note.published for note in notes)

    with ThreadPoolExecutor(max_workers=8) as pool:
        found = list(pool.map(dated, urls))
    return next((url for url, ok in zip(urls, found) if ok), None)
