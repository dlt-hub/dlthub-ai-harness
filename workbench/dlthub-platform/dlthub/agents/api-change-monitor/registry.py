"""APIs whose release notes the hook knows how to find and read.

Built-in entries ship here; a workspace adds or replaces entries in the
`[api_change_monitor.sources.<name>]` sections of `.dlt/config.toml`, which the
`add-api-change-source` skill writes. An API listed nowhere is still watched by its host.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class KnownApi:
    name: str
    hosts: "re.Pattern[str]"
    modules: "re.Pattern[str]"
    sources: List[str]
    # feed categories worth reading; empty reads every item
    topics: List[str] = field(default_factory=list)
    # pulls a release label out of a page that carries no dates
    version: Optional["re.Pattern[str]"] = None
    # the entry comes from the workspace's config rather than this file
    workspace: bool = False


_NETSUITE_HELP = "https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help"

KNOWN_APIS: Dict[str, KnownApi] = {
    api.name: api
    for api in [
        KnownApi(
            "shopify",
            re.compile(r"(^|\.)(myshopify|shopify)\.com$"),
            re.compile(r"shopify"),
            ["https://shopify.dev/changelog/feed.xml"],
            topics=["Admin GraphQL API", "Admin REST API", "Events & webhooks", "ShopifyQL"],
        ),
        KnownApi(
            "stripe",
            re.compile(r"(^|\.)stripe\.com$"),
            re.compile(r"stripe"),
            ["https://docs.stripe.com/changelog.md"],
        ),
        KnownApi(
            "github",
            re.compile(r"^api\.github\.com$"),
            re.compile(r"github"),
            [
                "https://docs.github.com/api/article/body"
                "?pathname=/en/rest/about-the-rest-api/breaking-changes"
            ],
        ),
        KnownApi(
            "hubspot",
            re.compile(r"(^|\.)(hubapi|hubspot)\.com$"),
            re.compile(r"hubspot"),
            ["https://developers.hubspot.com/changelog/rss.xml"],
        ),
        KnownApi(
            "amazon-sp-api",
            re.compile(r"^sellingpartnerapi(-[a-z]+)?\.amazon\.com$"),
            re.compile(r"sp_api|selling_partner|sellingpartner"),
            [
                "https://developer-docs.amazon.com/sp-api/docs/sp-api-release-notes.md",
                "https://developer-docs.amazon.com/sp-api/docs/sp-api-deprecations.md",
                "https://developer-docs.amazon.com/sp-api/changelog.rss",
            ],
        ),
        KnownApi(
            "zendesk",
            re.compile(r"(^|\.)zendesk\.com$"),
            re.compile(r"zendesk"),
            ["https://developer.zendesk.com/api-reference/changelog/changelog/"],
        ),
        KnownApi(
            "salesforce",
            re.compile(r"(^|\.)(salesforce|force)\.com$"),
            re.compile(r"salesforce"),
            [
                "https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest"
                "/api_rest_eol.htm"
            ],
        ),
        KnownApi(
            "pipedrive",
            re.compile(r"(^|\.)pipedrive\.com$"),
            re.compile(r"pipedrive"),
            ["https://developers.pipedrive.com/changelog"],
        ),
        KnownApi(
            "google-ads",
            re.compile(r"^googleads\.googleapis\.com$"),
            re.compile(r"google_ads|googleads"),
            [
                "https://developers.google.com/google-ads/api/docs/release-notes",
                "https://developers.google.com/google-ads/api/docs/sunset-dates",
            ],
        ),
        KnownApi(
            "jira",
            re.compile(r"\.atlassian\.net$|^api\.atlassian\.com$"),
            re.compile(r"jira"),
            ["https://developer.atlassian.com/cloud/jira/platform/changelog/"],
        ),
        KnownApi(
            "netsuite",
            re.compile(r"(^|\.)netsuite\.com$"),
            re.compile(r"netsuite|suiteql|suitetalk"),
            [
                f"{_NETSUITE_HELP}/section_N3950559.html",
                f"{_NETSUITE_HELP}/section_N3949039.html",
            ],
            version=re.compile(r"NetSuite (\d{4}\.\d) Release Notes"),
        ),
    ]
}

# hosts a pipeline names that are not data APIs: docs, package indexes, dltHub itself
IGNORED_HOSTS = re.compile(
    r"(^|\.)(dlthub\.com|dlthub\.io|pypi\.org|python\.org|w3\.org|json-schema\.org"
    r"|example\.(com|org)|localhost|readthedocs\.io)$|^github\.com$|^docs\.|^127\.0\.0\.1$"
)


WORKSPACE_SECTION = ("api_change_monitor", "sources")
_NEVER = re.compile(r"(?!)")


def _host_pattern(hosts: List[str]) -> "re.Pattern[str]":
    """A pattern matching each host and its subdomains, `*.` prefixes dropped."""
    names = [re.escape(str(h).strip().lower().lstrip("*.")) for h in hosts if str(h).strip()]
    return re.compile(rf"(^|\.)({'|'.join(names)})$") if names else _NEVER


def _workspace_entry(name: str, entry: Any) -> Optional[KnownApi]:
    """One `[api_change_monitor.sources.<name>]` section as an API, or None when unusable."""
    if not isinstance(entry, dict):
        return None
    urls = [str(u).strip() for u in entry.get("urls") or [] if str(u).strip().startswith("http")]
    if not urls:
        return None
    modules = [re.escape(str(m).strip().lower()) for m in entry.get("modules") or [] if str(m).strip()]
    try:
        version = re.compile(str(entry["version"])) if entry.get("version") else None
    except re.error:
        version = None
    return KnownApi(
        name=name.lower(),
        hosts=_host_pattern(list(entry.get("hosts") or [])),
        modules=re.compile("|".join(modules)) if modules else _NEVER,
        sources=urls,
        topics=[str(t) for t in entry.get("topics") or []],
        version=version,
        workspace=True,
    )


def load(root: Optional[Path] = None) -> Dict[str, KnownApi]:
    """The built-in APIs with the workspace's own entries laid over them by name."""
    apis = dict(KNOWN_APIS)
    path = (root or Path.cwd()) / ".dlt" / "config.toml"
    try:
        import tomlkit

        section: Any = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
        for key in WORKSPACE_SECTION:
            section = section.get(key) or {}
    except Exception:  # no config, or one that does not parse, leaves the built-ins
        return apis
    for name, entry in section.items():
        if api := _workspace_entry(str(name), entry):
            apis[api.name] = api
    return apis


def match_host(host: str, apis: Optional[Dict[str, KnownApi]] = None) -> Optional[KnownApi]:
    """The known API a host belongs to, workspace entries first, or None."""
    entries = sorted((apis or KNOWN_APIS).values(), key=lambda api: not api.workspace)
    return next((api for api in entries if api.hosts.search(host)), None)


def match_module(module: str, apis: Optional[Dict[str, KnownApi]] = None) -> Optional[KnownApi]:
    """The known API an imported module name belongs to, workspace entries first, or None."""
    entries = sorted((apis or KNOWN_APIS).values(), key=lambda api: not api.workspace)
    return next((api for api in entries if api.modules.search(module.lower())), None)
