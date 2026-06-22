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


def render(df: pd.DataFrame) -> None:
    # st.header("Cost per booking per channel")

    if df.empty:
        st.warning("No cost-per-booking data available for the selected filters.")
        return

    required_columns = {
        "performance_date",
        "channel",
        "bookings_count",
        "marketing_spend",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        st.error(
            "The cost-per-booking section is missing required columns: "
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

    daily_cpb_df = (
        chart_df
        .groupby(
            ["performance_date", "channel_display"],
            as_index=False,
        )
        .agg(
            bookings_count=("bookings_count", "sum"),
            marketing_spend=("marketing_spend", "sum"),
        )
    )

    daily_cpb_df["cost_per_booking"] = daily_cpb_df.apply(
        lambda row: (
            row["marketing_spend"] / row["bookings_count"]
            if row["bookings_count"] > 0
            else None
        ),
        axis=1,
    )

    daily_cpb_df["cost_per_booking"] = pd.to_numeric(
        daily_cpb_df["cost_per_booking"],
        errors="coerce",
    )

    daily_cpb_df["bookings_count"] = pd.to_numeric(
        daily_cpb_df["bookings_count"],
        errors="coerce",
    )

    daily_cpb_df["marketing_spend"] = pd.to_numeric(
        daily_cpb_df["marketing_spend"],
        errors="coerce",
    )

    daily_cpb_df["performance_date"] = pd.to_datetime(
        daily_cpb_df["performance_date"],
        errors="coerce",
    )

    cpb_trend_df = (
        daily_cpb_df
        .dropna(subset=["performance_date", "cost_per_booking"])
        .sort_values(["performance_date", "channel_display"])
        .reset_index(drop=True)
    )

    channel_summary_df = (
        daily_cpb_df
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

    channel_summary_df = channel_summary_df.sort_values(
        "cost_per_booking",
        ascending=True,
        na_position="last",
    )

    total_bookings = int(channel_summary_df["bookings_count"].sum())
    total_spend = float(channel_summary_df["marketing_spend"].sum())

    overall_cpb = (
        total_spend / total_bookings
        if total_bookings > 0
        else None
    )

    best_channel_row = (
        channel_summary_df.dropna(subset=["cost_per_booking"]).head(1)
    )

    best_channel = (
        best_channel_row.iloc[0]["channel_display"]
        if not best_channel_row.empty
        else "N/A"
    )

    best_channel_cpb = (
        best_channel_row.iloc[0]["cost_per_booking"]
        if not best_channel_row.empty
        else None
    )

    # col1, col2, col3 = st.columns(3)

    # col1.metric("Total spend", _format_currency(total_spend))
    # col2.metric("Overall cost per booking", _format_currency(overall_cpb))
    # col3.metric(
    #     "Best CPB channel",
    #     best_channel,
    #     _format_currency(best_channel_cpb),
    # )

    st.subheader("Cost per booking trend by channel")

    cpb_trend_df = daily_cpb_df.dropna(
        subset=["cost_per_booking"]
    ).sort_values(
        ["performance_date", "channel_display"]
    )

    if cpb_trend_df.empty:
        st.info(
            "No cost-per-booking trend is available because there are no days "
            "with both spend and bookings."
        )
    else:
        cpb_line_chart = (
            alt.Chart(cpb_trend_df)
            .mark_line(point=True)
            .encode(
                x=alt.X(
                    "performance_date:T",
                    title="Date",
                ),
                y=alt.Y(
                    "cost_per_booking:Q",
                    title="Cost per booking",
                    axis=alt.Axis(format="$,.2f"),
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
                ],
            )
            .properties(
                height=375,
            )
        )
        # st.write("CPB trend rows:", len(cpb_trend_df))
        # st.write(cpb_trend_df.dtypes)
        # st.dataframe(cpb_trend_df, width="stretch")
        st.altair_chart(cpb_line_chart, width="stretch")

    st.subheader("Average cost per booking by channel")

    cpb_bar_df = channel_summary_df.dropna(
        subset=["cost_per_booking"]
    )

    if cpb_bar_df.empty:
        st.info("No channel-level cost-per-booking values are available.")
    else:
        cpb_bar_chart = (
            alt.Chart(cpb_bar_df)
            .mark_bar()
            .encode(
                x=alt.X(
                    "cost_per_booking:Q",
                    title="Cost per booking",
                    axis=alt.Axis(format="$,.2f"),
                ),
                y=alt.Y(
                    "channel_display:N",
                    title="Channel",
                    sort="x",
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
                ],
            )
            .properties(
                height=250,
            )
        )

        st.altair_chart(cpb_bar_chart, width="stretch")

    with st.expander("Cost per booking summary data"):
        display_df = channel_summary_df.copy()

        display_df["marketing_spend"] = display_df[
            "marketing_spend"
        ].map(_format_currency)

        display_df["cost_per_booking"] = display_df[
            "cost_per_booking"
        ].map(_format_currency)

        display_df = display_df.rename(
            columns={
                "channel_display": "Channel",
                "bookings_count": "Bookings",
                "marketing_spend": "Spend",
                "cost_per_booking": "Cost Per Booking",
            }
        )

        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
        )

    with st.expander("Daily cost per booking data"):
        daily_display_df = daily_cpb_df.copy()

        daily_display_df["marketing_spend"] = daily_display_df[
            "marketing_spend"
        ].map(_format_currency)

        daily_display_df["cost_per_booking"] = daily_display_df[
            "cost_per_booking"
        ].map(_format_currency)

        daily_display_df = daily_display_df.rename(
            columns={
                "performance_date": "Date",
                "channel_display": "Channel",
                "bookings_count": "Bookings",
                "marketing_spend": "Spend",
                "cost_per_booking": "Cost Per Booking",
            }
        )

        st.dataframe(
            daily_display_df,
            width="stretch",
            hide_index=True,
        )