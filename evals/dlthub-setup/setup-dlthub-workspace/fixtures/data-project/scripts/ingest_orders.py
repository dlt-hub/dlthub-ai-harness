"""Pull Shopify orders into data/orders.csv, run nightly by cron."""

import os

import pandas as pd
import requests

SHOP = os.environ["SHOPIFY_SHOP"]
TOKEN = os.environ["SHOPIFY_TOKEN"]


def fetch_orders() -> list[dict]:
    """Fetch all orders, following the Link header pagination."""
    url = f"https://{SHOP}.myshopify.com/admin/api/2024-10/orders.json?limit=250&status=any"
    rows: list[dict] = []
    while url:
        resp = requests.get(url, headers={"X-Shopify-Access-Token": TOKEN}, timeout=30)
        resp.raise_for_status()
        rows.extend(resp.json()["orders"])
        url = resp.links.get("next", {}).get("url")
    return rows


if __name__ == "__main__":
    pd.json_normalize(fetch_orders()).to_csv("data/orders.csv", index=False)
