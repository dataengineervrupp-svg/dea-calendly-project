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


def render(df: pd.DataFrame) -> None:
    st.header("Daily calls booked by source / channel")

    if df.empty:
        st.warning("No booking data available for the selected filters.")
        return

    required_columns = {
        "performance_date",
        "channel",
        "bookings_count",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        st.error(
            "The daily calls chart is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
        return

    chart_df = df.copy()

    chart_df["performance_date"] = pd.to_datetime(
        chart_df["performance_date"]
    )

    chart_df["channel_display"] = chart_df["channel"].apply(
        _format_channel_name
    )

    daily_channel_df = (
        chart_df
        .groupby(
            ["performance_date", "channel_display"],
            as_index=False,
        )
        .agg(
            bookings_count=("bookings_count", "sum"),
        )
        .sort_values(["performance_date", "channel_display"])
    )

    total_bookings = int(daily_channel_df["bookings_count"].sum())

    active_days = daily_channel_df[
        daily_channel_df["bookings_count"] > 0
    ]["performance_date"].nunique()

    avg_bookings_per_day = (
        total_bookings / active_days
        if active_days > 0
        else 0
    )

    top_channel_df = (
        daily_channel_df
        .groupby("channel_display", as_index=False)
        .agg(bookings_count=("bookings_count", "sum"))
        .sort_values("bookings_count", ascending=False)
    )

    top_channel = (
        top_channel_df.iloc[0]["channel_display"]
        if not top_channel_df.empty
        else "N/A"
    )

    top_channel_bookings = (
        int(top_channel_df.iloc[0]["bookings_count"])
        if not top_channel_df.empty
        else 0
    )

    col1, col2, col3 = st.columns(3)

    col1.metric("Bookings in selection", f"{total_bookings:,}")
    col2.metric("Avg bookings / active day", f"{avg_bookings_per_day:,.1f}")
    col3.metric(
        "Top channel",
        top_channel,
        f"{top_channel_bookings:,} bookings",
    )

    st.subheader("Daily bookings trend by channel")

    daily_line_chart = (
        alt.Chart(daily_channel_df)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "performance_date:T",
                title="Date",
            ),
            y=alt.Y(
                "bookings_count:Q",
                title="Bookings",
            ),
            color=alt.Color(
                "channel_display:N",
                title="Channel",
            ),
            tooltip=[
                alt.Tooltip(
                    "performance_date:T",
                    title="Date",
                    format="%Y-%m-%d",
                ),
                alt.Tooltip(
                    "channel_display:N",
                    title="Channel",
                ),
                alt.Tooltip(
                    "bookings_count:Q",
                    title="Bookings",
                    format=",",
                ),
            ],
        )
        .properties(
            height=375,
        )
    )

    st.altair_chart(daily_line_chart, width="stretch")

    st.subheader("Bookings by channel")

    channel_summary_df = (
        daily_channel_df
        .groupby("channel_display", as_index=False)
        .agg(bookings_count=("bookings_count", "sum"))
        .sort_values("bookings_count", ascending=False)
    )

    channel_bar_chart = (
        alt.Chart(channel_summary_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "bookings_count:Q",
                title="Total bookings",
            ),
            y=alt.Y(
                "channel_display:N",
                title="Channel",
                sort="-x",
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
            ],
        )
        .properties(
            height=250,
        )
    )

    st.altair_chart(channel_bar_chart, width="stretch")

    with st.expander("Daily channel booking data"):
        st.dataframe(
            daily_channel_df.rename(
                columns={
                    "performance_date": "Date",
                    "channel_display": "Channel",
                    "bookings_count": "Bookings",
                }
            ),
            width="stretch",
            hide_index=True,
        )