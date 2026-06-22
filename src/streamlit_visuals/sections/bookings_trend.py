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
    st.header("Bookings trend over time")

    if df.empty:
        st.warning("No bookings trend data available for the selected filters.")
        return

    required_columns = {
        "performance_date",
        "channel",
        "bookings_count",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        st.error(
            "The bookings trend section is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
        return

    trend_df = df.copy()

    trend_df["performance_date"] = pd.to_datetime(
        trend_df["performance_date"],
        errors="coerce",
    )

    trend_df["bookings_count"] = pd.to_numeric(
        trend_df["bookings_count"],
        errors="coerce",
    ).fillna(0)

    trend_df["channel_display"] = trend_df["channel"].apply(
        _format_channel_name
    )

    trend_df = trend_df.dropna(subset=["performance_date"])

    if trend_df.empty:
        st.warning("No valid dated booking records are available.")
        return

    daily_total_df = (
        trend_df
        .groupby("performance_date", as_index=False)
        .agg(bookings_count=("bookings_count", "sum"))
        .sort_values("performance_date")
    )

    daily_total_df["bookings_7_day_avg"] = (
        daily_total_df["bookings_count"]
        .rolling(7, min_periods=1)
        .mean()
    )

    daily_channel_df = (
        trend_df
        .groupby(
            ["performance_date", "channel_display"],
            as_index=False,
        )
        .agg(bookings_count=("bookings_count", "sum"))
        .sort_values(["channel_display", "performance_date"])
    )

    # Fill missing date/channel combinations with zero bookings so rolling
    # averages are continuous rather than skipping missing days.
    all_dates = pd.date_range(
        start=daily_channel_df["performance_date"].min(),
        end=daily_channel_df["performance_date"].max(),
        freq="D",
    )

    all_channels = sorted(daily_channel_df["channel_display"].unique())

    complete_index = pd.MultiIndex.from_product(
        [all_dates, all_channels],
        names=["performance_date", "channel_display"],
    )

    daily_channel_df = (
        daily_channel_df
        .set_index(["performance_date", "channel_display"])
        .reindex(complete_index, fill_value=0)
        .reset_index()
        .sort_values(["channel_display", "performance_date"])
    )

    daily_channel_df["bookings_7_day_avg"] = (
        daily_channel_df
        .groupby("channel_display")["bookings_count"]
        .transform(lambda s: s.rolling(7, min_periods=1).mean())
    )

    weekly_channel_df = (
        daily_channel_df
        .set_index("performance_date")
        .groupby("channel_display")
        .resample("W-MON")["bookings_count"]
        .sum()
        .reset_index()
        .rename(columns={"performance_date": "week_start_date"})
        .sort_values(["week_start_date", "channel_display"])
    )

    total_bookings = int(daily_total_df["bookings_count"].sum())

    latest_day = daily_total_df["performance_date"].max()
    latest_day_bookings = int(
        daily_total_df.loc[
            daily_total_df["performance_date"] == latest_day,
            "bookings_count",
        ].sum()
    )

    latest_7_day_avg = (
        daily_total_df["bookings_7_day_avg"].iloc[-1]
        if not daily_total_df.empty
        else 0
    )

    first_7_day_avg = (
        daily_total_df["bookings_7_day_avg"].iloc[0]
        if not daily_total_df.empty
        else 0
    )

    avg_delta = latest_7_day_avg - first_7_day_avg

    col1, col2, col3 = st.columns(3)

    col1.metric("Total bookings", f"{total_bookings:,}")
    col2.metric(
        "Latest daily bookings",
        f"{latest_day_bookings:,}",
        latest_day.strftime("%Y-%m-%d"),
    )
    col3.metric(
        "Current 7-day avg",
        f"{latest_7_day_avg:,.1f}",
        f"{avg_delta:+,.1f} vs start",
    )

    st.subheader("Overall bookings trend")

    overall_base = alt.Chart(daily_total_df).encode(
        x=alt.X(
            "performance_date:T",
            title="Date",
        ),
        tooltip=[
            alt.Tooltip(
                "performance_date:T",
                title="Date",
                format="%Y-%m-%d",
            ),
            alt.Tooltip(
                "bookings_count:Q",
                title="Daily bookings",
                format=",",
            ),
            alt.Tooltip(
                "bookings_7_day_avg:Q",
                title="7-day average",
                format=",.1f",
            ),
        ],
    )

    daily_points = overall_base.mark_bar(opacity=0.35).encode(
        y=alt.Y(
            "bookings_count:Q",
            title="Bookings",
        ),
    )

    moving_average_line = overall_base.mark_line(point=True).encode(
        y=alt.Y(
            "bookings_7_day_avg:Q",
            title="Bookings",
        ),
    )

    overall_chart = (
        daily_points + moving_average_line
    ).properties(
        height=350,
    )

    st.altair_chart(overall_chart, width="stretch")

    st.subheader("7-day moving average by channel")

    channel_moving_average_chart = (
        alt.Chart(daily_channel_df)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "performance_date:T",
                title="Date",
            ),
            y=alt.Y(
                "bookings_7_day_avg:Q",
                title="7-day average bookings",
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
                    title="Daily bookings",
                    format=",",
                ),
                alt.Tooltip(
                    "bookings_7_day_avg:Q",
                    title="7-day average",
                    format=",.1f",
                ),
            ],
        )
        .properties(
            height=375,
        )
    )

    st.altair_chart(channel_moving_average_chart, width="stretch")

    st.subheader("Weekly bookings by channel")

    weekly_chart = (
        alt.Chart(weekly_channel_df)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "week_start_date:T",
                title="Week starting",
            ),
            y=alt.Y(
                "bookings_count:Q",
                title="Weekly bookings",
            ),
            color=alt.Color(
                "channel_display:N",
                title="Channel",
            ),
            tooltip=[
                alt.Tooltip(
                    "week_start_date:T",
                    title="Week starting",
                    format="%Y-%m-%d",
                ),
                alt.Tooltip(
                    "channel_display:N",
                    title="Channel",
                ),
                alt.Tooltip(
                    "bookings_count:Q",
                    title="Weekly bookings",
                    format=",",
                ),
            ],
        )
        .properties(
            height=350,
        )
    )

    st.altair_chart(weekly_chart, width="stretch")

    with st.expander("Daily trend data"):
        daily_display_df = daily_total_df.copy()

        daily_display_df = daily_display_df.rename(
            columns={
                "performance_date": "Date",
                "bookings_count": "Daily Bookings",
                "bookings_7_day_avg": "7-Day Average",
            }
        )

        st.dataframe(
            daily_display_df,
            width="stretch",
            hide_index=True,
        )

    with st.expander("Channel moving average data"):
        channel_display_df = daily_channel_df.copy()

        channel_display_df = channel_display_df.rename(
            columns={
                "performance_date": "Date",
                "channel_display": "Channel",
                "bookings_count": "Daily Bookings",
                "bookings_7_day_avg": "7-Day Average",
            }
        )

        st.dataframe(
            channel_display_df,
            width="stretch",
            hide_index=True,
        )

    with st.expander("Weekly channel trend data"):
        weekly_display_df = weekly_channel_df.copy()

        weekly_display_df = weekly_display_df.rename(
            columns={
                "week_start_date": "Week Starting",
                "channel_display": "Channel",
                "bookings_count": "Weekly Bookings",
            }
        )

        st.dataframe(
            weekly_display_df,
            width="stretch",
            hide_index=True,
        )