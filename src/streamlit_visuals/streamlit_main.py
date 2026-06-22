import streamlit as st
import pandas as pd

from sections import daily_calls_by_channel, cost_per_booking, bookings_trend, channel_leaderboard

GOLD_DAILY_CHANNEL_PERFORMANCE_PATH = (
    "s3://calendly-project-467875655273-us-east-1-an/"
    "gold/dashboard_exports/daily_channel_performance/"
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

    return df


def render_sidebar(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")

    filtered_df = df.copy()

    if "performance_date" in filtered_df.columns:
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

        filtered_df = filtered_df[
            filtered_df["channel"].isin(selected_channels)
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


def render_empty_dashboard_sections(df: pd.DataFrame) -> None:
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
        st.header("Booking volume by time slot / day of week")
        st.info("Placeholder: this will use a future booking time-patterns gold table.")

    with tab6:
        st.header("Meeting load per employee")
        st.info("Placeholder: this will use a future employee meeting-load gold table.")


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

    filtered_df = render_sidebar(df)

    render_kpis(filtered_df)

    st.divider()

    render_empty_dashboard_sections(filtered_df)

    with st.expander("Preview filtered data"):
        st.dataframe(filtered_df, width="stretch")


if __name__ == "__main__":
    main()