import streamlit as st
import pandas as pd

from sections import daily_calls_by_channel, cost_per_booking, bookings_trend, channel_leaderboard, booking_time_patterns, employee_meeting_load

GOLD_DAILY_CHANNEL_PERFORMANCE_PATH = (
    "s3://calendly-project-467875655273-us-east-1-an/"
    "gold/dashboard_exports/daily_channel_performance/"
)
GOLD_BOOKING_TIME_PATTERNS_PATH = (
    "s3://calendly-project-467875655273-us-east-1-an/"
    "gold/dashboard_exports/booking_time_patterns/"
)
GOLD_EMPLOYEE_MEETING_LOAD_PATH = (
    "s3://calendly-project-467875655273-us-east-1-an/"
    "gold/dashboard_exports/employee_meeting_load/"
)

st.set_page_config(
    page_title="Calendly Channel Performance Dashboard",
    page_icon="📅",
    layout="wide",
)

@st.cache_data(ttl=300)
def load_daily_channel_performance(path: str) -> pd.DataFrame:
    """
    Load the dashboard-friendly gold Parquet export.

    This assumes your EMR gold job writes a plain Parquet export
    in addition to the Delta table.
    """

    df = pd.read_parquet(path)

    if "performance_date" in df.columns:
        df["performance_date"] = pd.to_datetime(df["performance_date"])

    if "channel" in df.columns:
        df["channel"] = (
            df["channel"]
            .fillna("unknown")
            .replace("", "unknown")
        )

    return df

@st.cache_data(ttl=300)
def load_booking_time_patterns(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)

    if "booking_date" in df.columns:
        df["booking_date"] = pd.to_datetime(df["booking_date"])

    return df

@st.cache_data(ttl=300)
def load_employee_meeting_load(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)

    if "week_start_date" in df.columns:
        df["week_start_date"] = pd.to_datetime(
            df["week_start_date"],
            errors="coerce",
        )

    if "user_email" in df.columns:
        df["user_email"] = (
            df["user_email"]
            .fillna("unknown")
            .replace("", "unknown")
        )

    return df

def render_sidebar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    st.sidebar.header("Filters")

    filtered_df = df.copy()

    filter_state = {
        "start_date": None,
        "end_date": None,
        "selected_channels": None,
    }

    if "performance_date" in filtered_df.columns:
        filtered_df["performance_date"] = pd.to_datetime(
            filtered_df["performance_date"],
            errors="coerce",
        )

        min_date = filtered_df["performance_date"].min().date()
        max_date = filtered_df["performance_date"].max().date()

        selected_date_range = st.sidebar.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        if len(selected_date_range) == 2:
            start_date, end_date = selected_date_range

            filter_state["start_date"] = start_date
            filter_state["end_date"] = end_date

            filtered_df = filtered_df[
                (filtered_df["performance_date"].dt.date >= start_date)
                & (filtered_df["performance_date"].dt.date <= end_date)
            ]

    if "channel" in filtered_df.columns:
        channels = sorted(
            channel
            for channel in filtered_df["channel"].dropna().unique()
        )

        selected_channels = st.sidebar.multiselect(
            "Channels",
            options=channels,
            default=channels,
        )

        filter_state["selected_channels"] = selected_channels

        filtered_df = filtered_df[
            filtered_df["channel"].isin(selected_channels)
        ]

    return filtered_df, filter_state

def apply_filters_to_time_patterns(
    df: pd.DataFrame,
    filter_state: dict,
) -> pd.DataFrame:
    filtered_df = df.copy()

    if filtered_df.empty:
        return filtered_df

    if "booking_date" in filtered_df.columns:
        filtered_df["booking_date"] = pd.to_datetime(
            filtered_df["booking_date"],
            errors="coerce",
        )

    start_date = filter_state.get("start_date")
    end_date = filter_state.get("end_date")

    if (
        start_date is not None
        and end_date is not None
        and "booking_date" in filtered_df.columns
    ):
        filtered_df = filtered_df[
            (filtered_df["booking_date"].dt.date >= start_date)
            & (filtered_df["booking_date"].dt.date <= end_date)
        ]

    selected_channels = filter_state.get("selected_channels")

    if (
        selected_channels is not None
        and "channel" in filtered_df.columns
    ):
        filtered_df = filtered_df[
            filtered_df["channel"].isin(selected_channels)
        ]

    return filtered_df

def apply_filters_to_employee_meeting_load(
    df: pd.DataFrame,
    filter_state: dict,
) -> pd.DataFrame:
    filtered_df = df.copy()

    if filtered_df.empty:
        return filtered_df

    if "week_start_date" in filtered_df.columns:
        filtered_df["week_start_date"] = pd.to_datetime(
            filtered_df["week_start_date"],
            errors="coerce",
        )

    start_date = filter_state.get("start_date")
    end_date = filter_state.get("end_date")

    if (
        start_date is not None
        and end_date is not None
        and "week_start_date" in filtered_df.columns
    ):
        filtered_df = filtered_df[
            (filtered_df["week_start_date"].dt.date >= start_date)
            & (filtered_df["week_start_date"].dt.date <= end_date)
        ]

    return filtered_df

def render_kpis(df: pd.DataFrame) -> None:
    st.subheader("Overview")

    total_bookings = int(df["bookings_count"].sum()) if "bookings_count" in df.columns else 0
    total_spend = float(df["marketing_spend"].sum()) if "marketing_spend" in df.columns else 0.0

    overall_cpb = None
    if total_bookings > 0:
        overall_cpb = total_spend / total_bookings

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total bookings", f"{total_bookings:,}")
    col2.metric("Total spend", f"${total_spend:,.2f}")

    if overall_cpb is not None:
        col3.metric("Overall cost per booking", f"${overall_cpb:,.2f}")
    else:
        col3.metric("Overall cost per booking", "N/A")

    if "performance_date" in df.columns and not df.empty:
        col4.metric(
            "Date range",
            f"{df['performance_date'].min().date()} → {df['performance_date'].max().date()}",
        )
    else:
        col4.metric("Date range", "N/A")


def render_empty_dashboard_sections(df: pd.DataFrame, time_patterns_df: pd.DataFrame, employee_meeting_load_df: pd.DataFrame) -> None:
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            "1. Daily calls by channel",
            "2. Cost per booking",
            "3. Bookings trend",
            "4. Channel leaderboard",
            "5. Time slot / day of week",
            "6. Employee meeting load",
        ]
    )

    with tab1:
        # st.header("Daily calls booked by source / channel")
        # st.info("Placeholder: this will use the daily channel gold table.")
        daily_calls_by_channel.render(df)

    with tab2:
        # st.header("Cost per booking per channel")
        # st.info("Placeholder: this will calculate and visualize CPB by channel.")
        cost_per_booking.render(df)

    with tab3:
        # st.header("Bookings trend over time")
        # st.info("Placeholder: this will show booking volume over time.")
        bookings_trend.render(df)

    with tab4:
        # st.header("Channel attribution leaderboard")
        # st.info("Placeholder: this will rank channels by volume and cost per booking.")
        channel_leaderboard.render(df)

    with tab5:
        # st.header("Booking volume by time slot / day of week")
        # st.info("Placeholder: this will use a future booking time-patterns gold table.")
        booking_time_patterns.render(time_patterns_df)

    with tab6:
        # st.header("Meeting load per employee")
        # st.info("Placeholder: this will use a future employee meeting-load gold table.")
        employee_meeting_load.render(employee_meeting_load_df)


def main() -> None:
    st.title("Calendly Marketing Attribution Dashboard")

    st.caption(
        "Gold-layer dashboard for bookings, marketing spend, cost per booking, "
        "channel performance, time patterns, and meeting load."
    )

    try:
        df = load_daily_channel_performance(
            GOLD_DAILY_CHANNEL_PERFORMANCE_PATH
        )

    except Exception as exc:
        st.error("Could not load the gold daily channel performance data.")
        st.exception(exc)
        st.stop()
    
    time_patterns_df = load_booking_time_patterns(
       GOLD_BOOKING_TIME_PATTERNS_PATH
    )

    filtered_df, filter_state = render_sidebar(df)
    filtered_time_patterns_df = apply_filters_to_time_patterns(
        time_patterns_df,
        filter_state,
    )
    employee_meeting_load_df = load_employee_meeting_load(
        GOLD_EMPLOYEE_MEETING_LOAD_PATH
    )
    filtered_employee_meeting_load_df = apply_filters_to_employee_meeting_load(
        employee_meeting_load_df,
        filter_state,
    )

    render_kpis(filtered_df)

    st.divider()

    render_empty_dashboard_sections(filtered_df, filtered_time_patterns_df, filtered_employee_meeting_load_df)

    with st.expander("Preview filtered data"):
        st.dataframe(filtered_df, width="stretch")


if __name__ == "__main__":
    main()