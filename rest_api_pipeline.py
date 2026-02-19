from decimal import Decimal
from typing import Any, Optional

import dlt
from dlt.common.pendulum import pendulum
from dlt.sources.rest_api import (
    RESTAPIConfig,
    rest_api_resources,
)


@dlt.source(name="anthropic_admin")
def anthropic_admin_source(
    admin_key: str = dlt.secrets.value,
    starting_at: str = None,
    ending_at: str = None,
) -> Any:
    """Load data from the Anthropic Admin API.

    Covers: org members, invites, workspaces, API keys, usage report,
    cost report, and Claude Code analytics.

    Args:
        admin_key: Admin API key (sk-ant-admin...). Auto-loaded from secrets.toml.
        starting_at: Start of date range (ISO8601). Defaults to 30 days ago.
        ending_at: End of date range (ISO8601). Defaults to now.

    Example:
        pipeline.run(anthropic_admin_source())  # uses TOML credentials
        pipeline.run(anthropic_admin_source(starting_at="2025-01-01T00:00:00Z"))
    """
    if starting_at is None:
        starting_at = pendulum.now("UTC").subtract(days=30).start_of("day").to_iso8601_string()
    if ending_at is None:
        ending_at = pendulum.now("UTC").end_of("day").to_iso8601_string()

    # Claude Code analytics uses date-only format (single day = yesterday)
    cc_date = pendulum.now("UTC").subtract(days=1).to_date_string()

    config: RESTAPIConfig = {
        "client": {
            "base_url": "https://api.anthropic.com/v1/organizations/",
            "auth": {
                "type": "api_key",
                "name": "x-api-key",
                "api_key": admin_key,
                "location": "header",
            },
            "headers": {
                "anthropic-version": "2023-06-01",
            },
        },
        "resource_defaults": {
            "write_disposition": "replace",
        },
        "resources": [
            # --- Organization members ---
            {
                "name": "members",
                "endpoint": {
                    "path": "users",
                    "data_selector": "data",
                    "params": {"limit": 100},
                    # list endpoints use last_id → after_id cursor pagination
                    "paginator": {
                        "type": "cursor",
                        "cursor_path": "last_id",
                        "cursor_param": "after_id",
                    },
                },
                "primary_key": "id",
            },
            # --- Pending invites ---
            {
                "name": "invites",
                "endpoint": {
                    "path": "invites",
                    "data_selector": "data",
                    "params": {"limit": 100},
                    "paginator": {
                        "type": "cursor",
                        "cursor_path": "last_id",
                        "cursor_param": "after_id",
                    },
                },
                "primary_key": "id",
            },
            # --- Workspaces ---
            {
                "name": "workspaces",
                "endpoint": {
                    "path": "workspaces",
                    "data_selector": "data",
                    "params": {"limit": 100, "include_archived": False},
                    "paginator": {
                        "type": "cursor",
                        "cursor_path": "last_id",
                        "cursor_param": "after_id",
                    },
                },
                "primary_key": "id",
            },
            # --- API keys ---
            {
                "name": "api_keys",
                "endpoint": {
                    "path": "api_keys",
                    "data_selector": "data",
                    "params": {"limit": 100},
                    "paginator": {
                        "type": "cursor",
                        "cursor_path": "last_id",
                        "cursor_param": "after_id",
                    },
                },
                "primary_key": "id",
            },
            # --- Token usage report (grouped by model, daily) ---
            # Incremental: only fetches new daily buckets since the last run.
            {
                "name": "usage_report",
                "write_disposition": "append",
                "endpoint": {
                    "path": "usage_report/messages",
                    "data_selector": "data",
                    "params": {
                        "ending_at": ending_at,
                        "bucket_width": "1d",
                        "group_by[]": "model",
                        "limit": 31,
                    },
                    "incremental": {
                        "start_param": "starting_at",
                        "cursor_path": "starting_at",
                        "initial_value": starting_at,
                    },
                    # report endpoints use next_page token pagination
                    "paginator": {
                        "type": "cursor",
                        "cursor_path": "next_page",
                        "cursor_param": "page",
                    },
                },
            },
            # --- Cost report (grouped by workspace, daily) ---
            # Incremental: only fetches new daily buckets since the last run.
            {
                "name": "cost_report",
                "write_disposition": "append",
                "endpoint": {
                    "path": "cost_report",
                    "data_selector": "data",
                    "params": {
                        "ending_at": ending_at,
                        "group_by[]": "workspace_id",
                        "limit": 31,
                    },
                    "incremental": {
                        "start_param": "starting_at",
                        "cursor_path": "starting_at",
                        "initial_value": starting_at,
                    },
                    "paginator": {
                        "type": "cursor",
                        "cursor_path": "next_page",
                        "cursor_param": "page",
                    },
                },
                "processing_steps": [
                    {
                        "map": lambda item: {
                            **item,
                            "results": [
                                {**r, "amount": Decimal(r["amount"]) if r.get("amount") is not None else None}
                                for r in item.get("results", [])
                            ],
                        }
                    }
                ],
            },
            # --- Claude Code analytics (per-user, per-day) ---
            # Merge on (date, actor email) to safely handle re-runs on the same day.
            {
                "name": "claude_code_analytics",
                "write_disposition": "merge",
                "primary_key": ["date", "actor__email_address"],
                "endpoint": {
                    "path": "usage_report/claude_code",
                    "data_selector": "data",
                    "params": {
                        "starting_at": cc_date,
                        "limit": 100,
                    },
                    "paginator": {
                        "type": "cursor",
                        "cursor_path": "next_page",
                        "cursor_param": "page",
                    },
                },
            },
        ],
    }

    yield from rest_api_resources(config)


def load_anthropic_admin() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="anthropic_admin",
        destination="duckdb",
        dataset_name="anthropic_admin_data",
    )

    load_info = pipeline.run(
        anthropic_admin_source(),
    )
    print(load_info)  # noqa: T201


if __name__ == "__main__":
    load_anthropic_admin()
