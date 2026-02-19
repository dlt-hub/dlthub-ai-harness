import marimo

__generated_with = "0.19.11"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import dlt
    import altair as alt
    import pandas as pd

    return alt, dlt, mo, pd


@app.cell
def _(dlt):
    pipeline = dlt.attach("anthropic_admin")
    dataset = pipeline.dataset()
    return (dataset,)


@app.cell
def _(dataset):
    usage = dataset["usage_report"].to_ibis()
    ur = dataset["usage_report__results"].to_ibis()
    cost = dataset["cost_report"].to_ibis()
    cr = dataset["cost_report__results"].to_ibis()
    members = dataset["members"].to_ibis()
    api_keys = dataset["api_keys"].to_ibis()
    cc = dataset["claude_code_analytics"].to_ibis()
    ccm = dataset["claude_code_analytics__model_breakdown"].to_ibis()
    return api_keys, cc, ccm, cost, cr, members, ur, usage


@app.cell
def _(mo):
    mo.md("""
    # Anthropic Admin Dashboard
    """)
    return


@app.cell
def _(api_keys, cr, members, mo):
    total_cost = float(cr.amount.cast("float64").sum().execute())
    member_count = int(members.count().execute())
    key_count = int(api_keys.count().execute())
    mo.hstack(
        [
            mo.stat(f"${total_cost:,.0f}", label="30-day Cost (USD)"),
            mo.stat(str(member_count), label="Team Members"),
            mo.stat(str(key_count), label="API Keys"),
        ],
        justify="start",
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## Daily Cost (USD)
    """)
    return


@app.cell
def _(alt, cost, cr, mo, pd):
    daily_cost_df = (
        cr.join(cost, cr._dlt_parent_id == cost._dlt_id)
        .group_by("starting_at")
        .aggregate(total_usd=cr.amount.cast("float64").sum())
        .order_by("starting_at")
        .execute()
    )
    daily_cost_df["starting_at"] = pd.to_datetime(daily_cost_df["starting_at"])

    daily_cost_chart = mo.ui.altair_chart(
        alt.Chart(daily_cost_df)
        .mark_bar(color="#4c78a8")
        .encode(
            x=alt.X("starting_at:T", title="Date", axis=alt.Axis(format="%b %d")),
            y=alt.Y("total_usd:Q", title="Cost (USD)"),
            tooltip=[
                alt.Tooltip("starting_at:T", title="Date", format="%b %d"),
                alt.Tooltip("total_usd:Q", title="Cost (USD)", format="$,.2f"),
            ],
        )
        .properties(height=280)
    )
    daily_cost_chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## Daily Output Tokens by Model
    """)
    return


@app.cell
def _(alt, mo, pd, ur, usage):
    usage_df = (
        ur.join(usage, ur._dlt_parent_id == usage._dlt_id)
        .group_by(["starting_at", "model"])
        .aggregate(
            output_tokens=ur.output_tokens.sum(),
            uncached_input=ur.uncached_input_tokens.sum(),
            cache_read=ur.cache_read_input_tokens.sum(),
        )
        .order_by("starting_at")
        .execute()
    )
    usage_df["starting_at"] = pd.to_datetime(usage_df["starting_at"])

    token_chart = mo.ui.altair_chart(
        alt.Chart(usage_df)
        .mark_bar()
        .encode(
            x=alt.X("starting_at:T", title="Date", axis=alt.Axis(format="%b %d")),
            y=alt.Y("output_tokens:Q", title="Output Tokens", stack=True),
            color=alt.Color("model:N", title="Model"),
            tooltip=[
                alt.Tooltip("starting_at:T", title="Date", format="%b %d"),
                "model:N",
                alt.Tooltip("output_tokens:Q", title="Output Tokens", format=","),
                alt.Tooltip("uncached_input:Q", title="Uncached Input", format=","),
                alt.Tooltip("cache_read:Q", title="Cache Read", format=","),
            ],
        )
        .properties(height=280)
    )
    token_chart
    return (usage_df,)


@app.cell
def _(mo):
    mo.md("""
    ## Cache Efficiency by Model
    """)
    return


@app.cell
def _(alt, mo, usage_df):
    cache_df = (
        usage_df.groupby("model", as_index=False)
        .agg(
            total_cache_read=("cache_read", "sum"),
            total_uncached=("uncached_input", "sum"),
            total_output=("output_tokens", "sum"),
        )
        .assign(
            cache_ratio=lambda df: df["total_cache_read"]
            / (df["total_cache_read"] + df["total_uncached"]).clip(lower=1)
        )
        .sort_values("cache_ratio", ascending=False)
    )

    cache_chart = mo.ui.altair_chart(
        alt.Chart(cache_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "cache_ratio:Q",
                axis=alt.Axis(format=".0%"),
                title="Cache Hit Rate  (cache_read / total_input)",
                scale=alt.Scale(domain=[0, 1]),
            ),
            y=alt.Y("model:N", sort="-x", title=""),
            color=alt.Color(
                "cache_ratio:Q",
                scale=alt.Scale(scheme="greens", domain=[0, 1]),
                legend=None,
            ),
            tooltip=[
                "model:N",
                alt.Tooltip("cache_ratio:Q", title="Cache Hit Rate", format=".1%"),
                alt.Tooltip("total_cache_read:Q", title="Cache Read Tokens", format=","),
                alt.Tooltip("total_uncached:Q", title="Uncached Input Tokens", format=","),
            ],
        )
        .properties(height=220)
    )
    cache_chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## Claude Code Team Activity (Yesterday)
    """)
    return


@app.cell
def _(alt, cc, mo):
    cc_df = cc.select(
        "actor__email_address",
        "core_metrics__num_sessions",
        "core_metrics__lines_of_code__added",
        "core_metrics__lines_of_code__removed",
        "core_metrics__commits_by_claude_code",
        "tool_actions__edit_tool__accepted",
        "tool_actions__edit_tool__rejected",
    ).execute()
    cc_df.columns = [
        "email",
        "sessions",
        "lines_added",
        "lines_removed",
        "commits",
        "edits_accepted",
        "edits_rejected",
    ]
    cc_df["accept_rate"] = (
        cc_df["edits_accepted"]
        / (cc_df["edits_accepted"] + cc_df["edits_rejected"]).clip(lower=1)
    )

    lines_chart = mo.ui.altair_chart(
        alt.Chart(cc_df)
        .mark_bar(color="#4c78a8")
        .encode(
            y=alt.Y("email:N", sort="-x", title=""),
            x=alt.X("lines_added:Q", title="Lines of Code Added"),
            tooltip=[
                "email:N",
                alt.Tooltip("lines_added:Q", title="Lines Added", format=","),
                alt.Tooltip("lines_removed:Q", title="Lines Removed", format=","),
                "sessions:Q",
                "commits:Q",
                alt.Tooltip("accept_rate:Q", title="Edit Accept Rate", format=".0%"),
            ],
        )
        .properties(height=200)
    )
    lines_chart
    return (cc_df,)


@app.cell
def _(mo):
    mo.md("""
    ### Edit Accept Rate by Developer
    """)
    return


@app.cell
def _(alt, cc_df, mo):
    accept_chart = mo.ui.altair_chart(
        alt.Chart(cc_df)
        .mark_bar()
        .encode(
            y=alt.Y("email:N", sort="-x", title=""),
            x=alt.X(
                "accept_rate:Q",
                axis=alt.Axis(format=".0%"),
                title="Edit Accept Rate",
                scale=alt.Scale(domain=[0, 1]),
            ),
            color=alt.Color(
                "accept_rate:Q",
                scale=alt.Scale(scheme="blues", domain=[0, 1]),
                legend=None,
            ),
            tooltip=[
                "email:N",
                alt.Tooltip("accept_rate:Q", title="Accept Rate", format=".0%"),
                "edits_accepted:Q",
                "edits_rejected:Q",
            ],
        )
        .properties(height=200)
    )
    accept_chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## Claude Code Cost by Model (Yesterday, cents)
    """)
    return


@app.cell
def _(alt, ccm, mo):
    ccm_df = (
        ccm.group_by("model")
        .aggregate(
            total_cost_cents=ccm.estimated_cost__amount.sum(),
            total_input=ccm.tokens__input.sum(),
            total_output=ccm.tokens__output.sum(),
        )
        .order_by(ccm.estimated_cost__amount.sum().desc())
        .execute()
    )

    cc_cost_chart = mo.ui.altair_chart(
        alt.Chart(ccm_df)
        .mark_bar()
        .encode(
            y=alt.Y("model:N", sort="-x", title=""),
            x=alt.X("total_cost_cents:Q", title="Estimated Cost (cents)"),
            color=alt.Color("model:N", legend=None),
            tooltip=[
                "model:N",
                alt.Tooltip("total_cost_cents:Q", title="Cost (¢)", format=","),
                alt.Tooltip("total_input:Q", title="Input Tokens", format=","),
                alt.Tooltip("total_output:Q", title="Output Tokens", format=","),
            ],
        )
        .properties(height=220)
    )
    cc_cost_chart
    return


if __name__ == "__main__":
    app.run()
