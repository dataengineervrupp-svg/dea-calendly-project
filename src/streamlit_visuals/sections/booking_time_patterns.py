import altair as alt
import pandas as pd
import streamlit as st


DAY_ORDER = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]

TIME_SLOT_ORDER = [
    "overnight",
    "early_morning",
    "morning",
    "afternoon",
    "evening",
    "late_evening",
]


def _format_channel_name(channel: str) -> str:
    if pd.isna(channel):
        return "Unknown"

    return (
        str(channel)
        .replace("_paid_ads", "")
        .replace("_", " ")
        .title()
    )


def _format_time_slot(time_slot: str) -> str:
    if pd.isna(time_slot):
        return "Unknown"

    return str(time_slot).replace("_", " ").title()


def _format_hour(hour_value: int | float | None) -> str:
    if hour_value is None or pd.isna(hour_value):
        return "Unknown"

    hour_int = int(hour_value)

    if hour_int == 0:
        return "12 AM"
    if hour_int < 12:
        return f"{hour_int} AM"
    if hour_int == 12:
        return "12 PM"

    return f"{hour_int - 12} PM"


def render(df: pd.DataFrame) -> None:
    st.header("Booking volume by time slot / day of week")

    if df.empty:
        st.warning("No booking time-pattern data available for the selected filters.")
        return

    required_columns = {
        "booking_date",
        "day_of_week_name",
        "day_of_week_number",
        "hour_of_day",
        "time_slot",
        "channel",
        "bookings_count",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        st.error(
            "The booking time-pattern section is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
        return

    patterns_df = df.copy()

    patterns_df["booking_date"] = pd.to_datetime(
        patterns_df["booking_date"],
        errors="coerce",
    )

    patterns_df["hour_of_day"] = pd.to_numeric(
        patterns_df["hour_of_day"],
        errors="coerce",
    )

    patterns_df["day_of_week_number"] = pd.to_numeric(
        patterns_df["day_of_week_number"],
        errors="coerce",
    )

    patterns_df["bookings_count"] = pd.to_numeric(
        patterns_df["bookings_count"],
        errors="coerce",
    ).fillna(0)

    patterns_df["channel_display"] = patterns_df["channel"].apply(
        _format_channel_name
    )

    patterns_df["hour_display"] = patterns_df["hour_of_day"].apply(
        _format_hour
    )

    patterns_df["time_slot_display"] = patterns_df["time_slot"].apply(
        _format_time_slot
    )

    patterns_df = patterns_df.dropna(
        subset=[
            "booking_date",
            "day_of_week_name",
            "hour_of_day",
        ]
    )

    if patterns_df.empty:
        st.warning("No valid booking time-pattern rows are available.")
        return

    total_bookings = int(patterns_df["bookings_count"].sum())

    busiest_hour_df = (
        patterns_df
        .groupby(["hour_of_day", "hour_display"], as_index=False)
        .agg(bookings_count=("bookings_count", "sum"))
        .sort_values("bookings_count", ascending=False)
    )

    busiest_day_df = (
        patterns_df
        .groupby(["day_of_week_number", "day_of_week_name"], as_index=False)
        .agg(bookings_count=("bookings_count", "sum"))
        .sort_values("bookings_count", ascending=False)
    )

    busiest_slot_df = (
        patterns_df
        .groupby(["time_slot", "time_slot_display"], as_index=False)
        .agg(bookings_count=("bookings_count", "sum"))
        .sort_values("bookings_count", ascending=False)
    )

    busiest_hour = (
        busiest_hour_df.iloc[0]["hour_display"]
        if not busiest_hour_df.empty
        else "N/A"
    )

    busiest_day = (
        busiest_day_df.iloc[0]["day_of_week_name"]
        if not busiest_day_df.empty
        else "N/A"
    )

    busiest_slot = (
        busiest_slot_df.iloc[0]["time_slot_display"]
        if not busiest_slot_df.empty
        else "N/A"
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total bookings", f"{total_bookings:,}")
    col2.metric("Busiest day", busiest_day)
    col3.metric("Busiest hour", busiest_hour)
    col4.metric("Busiest time slot", busiest_slot)

    st.subheader("Booking heatmap by day of week and hour")

    heatmap_hour_df = (
        patterns_df
        .groupby(
            [
                "day_of_week_name",
                "hour_of_day",
                "hour_display",
            ],
            as_index=False,
        )
        .agg(bookings_count=("bookings_count", "sum"))
    )

    heatmap_hour_chart = (
        alt.Chart(heatmap_hour_df)
        .mark_rect()
        .encode(
            x=alt.X(
                "hour_of_day:O",
                title="Hour of day",
                sort=list(range(24)),
                axis=alt.Axis(labelExpr="""
                    datum.value == 0 ? '12 AM' :
                    datum.value < 12 ? datum.value + ' AM' :
                    datum.value == 12 ? '12 PM' :
                    (datum.value - 12) + ' PM'
                """),
            ),
            y=alt.Y(
                "day_of_week_name:N",
                title="Day of week",
                sort=DAY_ORDER,
            ),
            color=alt.Color(
                "bookings_count:Q",
                title="Bookings",
                scale=alt.Scale(scheme="blues"),
            ),
            tooltip=[
                alt.Tooltip(
                    "day_of_week_name:N",
                    title="Day",
                ),
                alt.Tooltip(
                    "hour_display:N",
                    title="Hour",
                ),
                alt.Tooltip(
                    "bookings_count:Q",
                    title="Bookings",
                    format=",",
                ),
            ],
        )
        .properties(
            height=325,
        )
    )

    st.altair_chart(heatmap_hour_chart, width="stretch")

    st.subheader("Booking heatmap by day of week and time slot")

    heatmap_slot_df = (
        patterns_df
        .groupby(
            [
                "day_of_week_name",
                "time_slot",
                "time_slot_display",
            ],
            as_index=False,
        )
        .agg(bookings_count=("bookings_count", "sum"))
    )

    heatmap_slot_chart = (
        alt.Chart(heatmap_slot_df)
        .mark_rect()
        .encode(
            x=alt.X(
                "time_slot_display:N",
                title="Time slot",
                sort=[
                    _format_time_slot(slot)
                    for slot in TIME_SLOT_ORDER
                ],
            ),
            y=alt.Y(
                "day_of_week_name:N",
                title="Day of week",
                sort=DAY_ORDER,
            ),
            color=alt.Color(
                "bookings_count:Q",
                title="Bookings",
                scale=alt.Scale(scheme="greens"),
            ),
            tooltip=[
                alt.Tooltip(
                    "day_of_week_name:N",
                    title="Day",
                ),
                alt.Tooltip(
                    "time_slot_display:N",
                    title="Time slot",
                ),
                alt.Tooltip(
                    "bookings_count:Q",
                    title="Bookings",
                    format=",",
                ),
            ],
        )
        .properties(
            height=300,
        )
    )

    heatmap_slot_text = (
        alt.Chart(heatmap_slot_df)
        .mark_text()
        .encode(
            x=alt.X(
                "time_slot_display:N",
                sort=[
                    _format_time_slot(slot)
                    for slot in TIME_SLOT_ORDER
                ],
            ),
            y=alt.Y(
                "day_of_week_name:N",
                sort=DAY_ORDER,
            ),
            text=alt.Text(
                "bookings_count:Q",
                format=",",
            ),
        )
    )

    st.altair_chart(heatmap_slot_chart + heatmap_slot_text, width="stretch")

    st.subheader("Bookings by hour and channel")

    hourly_channel_df = (
        patterns_df
        .groupby(
            ["hour_of_day", "hour_display", "channel_display"],
            as_index=False,
        )
        .agg(bookings_count=("bookings_count", "sum"))
        .sort_values(["hour_of_day", "channel_display"])
    )

    hourly_channel_chart = (
        alt.Chart(hourly_channel_df)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "hour_of_day:O",
                title="Hour of day",
                sort=list(range(24)),
                axis=alt.Axis(labelExpr="""
                    datum.value == 0 ? '12 AM' :
                    datum.value < 12 ? datum.value + ' AM' :
                    datum.value == 12 ? '12 PM' :
                    (datum.value - 12) + ' PM'
                """),
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
                    "hour_display:N",
                    title="Hour",
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
            height=350,
        )
    )

    st.altair_chart(hourly_channel_chart, width="stretch")

    st.subheader("Bookings by day of week and channel")

    day_channel_df = (
        patterns_df
        .groupby(
            [
                "day_of_week_number",
                "day_of_week_name",
                "channel_display",
            ],
            as_index=False,
        )
        .agg(bookings_count=("bookings_count", "sum"))
        .sort_values(["day_of_week_number", "channel_display"])
    )

    day_channel_chart = (
        alt.Chart(day_channel_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "day_of_week_name:N",
                title="Day of week",
                sort=DAY_ORDER,
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
                    "day_of_week_name:N",
                    title="Day",
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
            height=350,
        )
    )

    st.altair_chart(day_channel_chart, width="stretch")

    with st.expander("Hourly booking heatmap data"):
        display_df = heatmap_hour_df.copy()

        display_df = display_df.rename(
            columns={
                "day_of_week_name": "Day",
                "hour_display": "Hour",
                "bookings_count": "Bookings",
            }
        )

        st.dataframe(
            display_df[["Day", "Hour", "Bookings"]],
            width="stretch",
            hide_index=True,
        )

    with st.expander("Time-slot booking heatmap data"):
        display_df = heatmap_slot_df.copy()

        display_df = display_df.rename(
            columns={
                "day_of_week_name": "Day",
                "time_slot_display": "Time Slot",
                "bookings_count": "Bookings",
            }
        )

        st.dataframe(
            display_df[["Day", "Time Slot", "Bookings"]],
            width="stretch",
            hide_index=True,
        )

    with st.expander("Raw booking time-pattern data"):
        display_df = patterns_df.copy()

        display_df = display_df.rename(
            columns={
                "booking_date": "Booking Date",
                "day_of_week_name": "Day",
                "hour_display": "Hour",
                "time_slot_display": "Time Slot",
                "channel_display": "Channel",
                "bookings_count": "Bookings",
                "event_type_code": "Event Type Code",
            }
        )

        columns_to_show = [
            "Booking Date",
            "Day",
            "Hour",
            "Time Slot",
            "Channel",
            "Bookings",
        ]

        if "Event Type Code" in display_df.columns:
            columns_to_show.append("Event Type Code")

        st.dataframe(
            display_df[columns_to_show],
            width="stretch",
            hide_index=True,
        )