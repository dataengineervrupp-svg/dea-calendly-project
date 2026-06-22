import altair as alt
import pandas as pd
import streamlit as st


def _format_channel_name(channel: str) -> str:
    if pd.isna(channel):
        return "Unknown"

    return (
        str(channel)
        .replace("_paid_ads", "")
        .replace("_", " ")
        .title()
    )


def _format_currency(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"

    return f"${value:,.2f}"


def _format_number(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"

    return f"{value:,.0f}"


def _add_rank_columns(df: pd.DataFrame) -> pd.DataFrame:
    ranked_df = df.copy()

    ranked_df["booking_rank"] = ranked_df["bookings_count"].rank(
        method="dense",
        ascending=False,
    )

    ranked_df["spend_rank"] = ranked_df["marketing_spend"].rank(
        method="dense",
        ascending=False,
    )

    ranked_df["cpb_rank"] = ranked_df["cost_per_booking"].rank(
        method="dense",
        ascending=True,
        na_option="bottom",
    )

    # Lower composite score is better:
    # high bookings, low CPB, and spend included as context.
    ranked_df["performance_score"] = (
        ranked_df["booking_rank"] + ranked_df["cpb_rank"]
    )

    ranked_df["overall_rank"] = ranked_df["performance_score"].rank(
        method="dense",
        ascending=True,
    )

    return ranked_df.sort_values(
        ["overall_rank", "cost_per_booking", "bookings_count"],
        ascending=[True, True, False],
    )


def render(df: pd.DataFrame) -> None:
    st.header("Channel attribution leaderboard")

    if df.empty:
        st.warning("No channel attribution data available for the selected filters.")
        return

    required_columns = {
        "channel",
        "bookings_count",
        "marketing_spend",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        st.error(
            "The channel leaderboard is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
        return

    leaderboard_df = df.copy()

    leaderboard_df["channel_display"] = leaderboard_df["channel"].apply(
        _format_channel_name
    )

    leaderboard_df["bookings_count"] = pd.to_numeric(
        leaderboard_df["bookings_count"],
        errors="coerce",
    ).fillna(0)

    leaderboard_df["marketing_spend"] = pd.to_numeric(
        leaderboard_df["marketing_spend"],
        errors="coerce",
    ).fillna(0)

    channel_summary_df = (
        leaderboard_df
        .groupby("channel_display", as_index=False)
        .agg(
            bookings_count=("bookings_count", "sum"),
            marketing_spend=("marketing_spend", "sum"),
        )
    )

    channel_summary_df["cost_per_booking"] = channel_summary_df.apply(
        lambda row: (
            row["marketing_spend"] / row["bookings_count"]
            if row["bookings_count"] > 0
            else None
        ),
        axis=1,
    )

    channel_summary_df["cost_per_booking"] = pd.to_numeric(
        channel_summary_df["cost_per_booking"],
        errors="coerce",
    )

    channel_summary_df = _add_rank_columns(channel_summary_df)

    total_bookings = int(channel_summary_df["bookings_count"].sum())
    total_spend = float(channel_summary_df["marketing_spend"].sum())

    overall_cpb = (
        total_spend / total_bookings
        if total_bookings > 0
        else None
    )

    best_volume_row = channel_summary_df.sort_values(
        "bookings_count",
        ascending=False,
    ).head(1)

    best_cpb_row = (
        channel_summary_df
        .dropna(subset=["cost_per_booking"])
        .sort_values("cost_per_booking")
        .head(1)
    )

    best_overall_row = channel_summary_df.sort_values(
        "overall_rank"
    ).head(1)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total bookings", _format_number(total_bookings))
    col2.metric("Total spend", _format_currency(total_spend))
    col3.metric("Overall CPB", _format_currency(overall_cpb))

    if not best_overall_row.empty:
        col4.metric(
            "Top overall channel",
            best_overall_row.iloc[0]["channel_display"],
            f"Rank #{int(best_overall_row.iloc[0]['overall_rank'])}",
        )
    else:
        col4.metric("Top overall channel", "N/A")

    insight_col1, insight_col2 = st.columns(2)

    with insight_col1:
        if not best_volume_row.empty:
            st.info(
                "Highest volume: "
                f"**{best_volume_row.iloc[0]['channel_display']}** "
                f"with **{int(best_volume_row.iloc[0]['bookings_count']):,}** bookings."
            )

    with insight_col2:
        if not best_cpb_row.empty:
            st.info(
                "Lowest cost per booking: "
                f"**{best_cpb_row.iloc[0]['channel_display']}** "
                f"at **{_format_currency(best_cpb_row.iloc[0]['cost_per_booking'])}**."
            )

    st.subheader("Leaderboard")

    display_leaderboard_df = channel_summary_df.copy()

    display_leaderboard_df["overall_rank"] = display_leaderboard_df[
        "overall_rank"
    ].astype(int)

    display_leaderboard_df["bookings_count"] = display_leaderboard_df[
        "bookings_count"
    ].astype(int)

    display_leaderboard_df["marketing_spend_display"] = display_leaderboard_df[
        "marketing_spend"
    ].map(_format_currency)

    display_leaderboard_df["cost_per_booking_display"] = display_leaderboard_df[
        "cost_per_booking"
    ].map(_format_currency)

    display_leaderboard_df = display_leaderboard_df[
        [
            "overall_rank",
            "channel_display",
            "bookings_count",
            "marketing_spend_display",
            "cost_per_booking_display",
        ]
    ].rename(
        columns={
            "overall_rank": "Rank",
            "channel_display": "Channel",
            "bookings_count": "Bookings",
            "marketing_spend_display": "Spend",
            "cost_per_booking_display": "Cost Per Booking",
        }
    )

    st.dataframe(
        display_leaderboard_df,
        width="stretch",
        hide_index=True,
    )

    st.subheader("Volume versus cost per booking")

    scatter_df = channel_summary_df.dropna(
        subset=["cost_per_booking"]
    ).copy()

    if scatter_df.empty:
        st.info(
            "No volume-versus-CPB chart is available because no channels have "
            "both spend and bookings."
        )
    else:
        scatter_chart = (
            alt.Chart(scatter_df)
            .mark_circle(size=250)
            .encode(
                x=alt.X(
                    "bookings_count:Q",
                    title="Total bookings",
                ),
                y=alt.Y(
                    "cost_per_booking:Q",
                    title="Cost per booking",
                    axis=alt.Axis(format="$,.2f"),
                ),
                size=alt.Size(
                    "marketing_spend:Q",
                    title="Spend",
                    legend=alt.Legend(format="$,.0f"),
                ),
                color=alt.Color(
                    "channel_display:N",
                    title="Channel",
                ),
                tooltip=[
                    alt.Tooltip(
                        "channel_display:N",
                        title="Channel",
                    ),
                    alt.Tooltip(
                        "bookings_count:Q",
                        title="Bookings",
                        format=",",
                    ),
                    alt.Tooltip(
                        "marketing_spend:Q",
                        title="Spend",
                        format="$,.2f",
                    ),
                    alt.Tooltip(
                        "cost_per_booking:Q",
                        title="Cost per booking",
                        format="$,.2f",
                    ),
                    alt.Tooltip(
                        "overall_rank:Q",
                        title="Rank",
                        format=".0f",
                    ),
                ],
            )
            .properties(
                height=375,
            )
        )

        st.altair_chart(scatter_chart, width="stretch")

    st.subheader("Channel performance heatmap")

    heatmap_df = channel_summary_df.copy()

    heatmap_long_df = heatmap_df.melt(
        id_vars=["channel_display"],
        value_vars=[
            "bookings_count",
            "marketing_spend",
            "cost_per_booking",
        ],
        var_name="metric",
        value_name="metric_value",
    )

    metric_labels = {
        "bookings_count": "Bookings",
        "marketing_spend": "Spend",
        "cost_per_booking": "CPB",
    }

    heatmap_long_df["metric_display"] = heatmap_long_df["metric"].map(
        metric_labels
    )

    # Normalize each metric independently for heatmap intensity.
    # For bookings and spend, higher = stronger.
    # For CPB, lower is better, so invert the normalized score.
    normalized_frames = []

    for metric_name, metric_df in heatmap_long_df.groupby("metric"):
        metric_df = metric_df.copy()

        metric_min = metric_df["metric_value"].min()
        metric_max = metric_df["metric_value"].max()

        if pd.isna(metric_min) or pd.isna(metric_max) or metric_min == metric_max:
            metric_df["normalized_score"] = 0.5
        else:
            metric_df["normalized_score"] = (
                (metric_df["metric_value"] - metric_min)
                / (metric_max - metric_min)
            )

        if metric_name == "cost_per_booking":
            metric_df["normalized_score"] = 1 - metric_df["normalized_score"]

        normalized_frames.append(metric_df)

    heatmap_long_df = pd.concat(normalized_frames, ignore_index=True)

    heatmap_long_df["metric_value_display"] = heatmap_long_df.apply(
        lambda row: (
            _format_currency(row["metric_value"])
            if row["metric"] in {"marketing_spend", "cost_per_booking"}
            else _format_number(row["metric_value"])
        ),
        axis=1,
    )

    heatmap_chart = (
        alt.Chart(heatmap_long_df)
        .mark_rect()
        .encode(
            x=alt.X(
                "metric_display:N",
                title="Metric",
                sort=["Bookings", "Spend", "CPB"],
            ),
            y=alt.Y(
                "channel_display:N",
                title="Channel",
                sort=alt.EncodingSortField(
                    field="normalized_score",
                    op="sum",
                    order="descending",
                ),
            ),
            color=alt.Color(
                "normalized_score:Q",
                title="Relative performance",
                scale=alt.Scale(scheme="blues"),
            ),
            tooltip=[
                alt.Tooltip(
                    "channel_display:N",
                    title="Channel",
                ),
                alt.Tooltip(
                    "metric_display:N",
                    title="Metric",
                ),
                alt.Tooltip(
                    "metric_value_display:N",
                    title="Value",
                ),
            ],
        )
        .properties(
            height=250,
        )
    )

    heatmap_text = (
        alt.Chart(heatmap_long_df)
        .mark_text()
        .encode(
            x=alt.X(
                "metric_display:N",
                sort=["Bookings", "Spend", "CPB"],
            ),
            y=alt.Y(
                "channel_display:N",
                sort=alt.EncodingSortField(
                    field="normalized_score",
                    op="sum",
                    order="descending",
                ),
            ),
            text="metric_value_display:N",
        )
    )

    st.altair_chart(heatmap_chart + heatmap_text, width="stretch")

    with st.expander("Channel leaderboard data"):
        raw_display_df = channel_summary_df.copy()

        raw_display_df["marketing_spend"] = raw_display_df[
            "marketing_spend"
        ].map(_format_currency)

        raw_display_df["cost_per_booking"] = raw_display_df[
            "cost_per_booking"
        ].map(_format_currency)

        raw_display_df = raw_display_df.rename(
            columns={
                "channel_display": "Channel",
                "bookings_count": "Bookings",
                "marketing_spend": "Spend",
                "cost_per_booking": "Cost Per Booking",
                "booking_rank": "Booking Rank",
                "spend_rank": "Spend Rank",
                "cpb_rank": "CPB Rank",
                "overall_rank": "Overall Rank",
            }
        )

        st.dataframe(
            raw_display_df,
            width="stretch",
            hide_index=True,
        )