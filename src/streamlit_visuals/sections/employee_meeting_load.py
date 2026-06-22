import altair as alt
import pandas as pd
import streamlit as st


def _format_employee_email(user_email: str) -> str:
    if pd.isna(user_email):
        return "Unknown"

    return str(user_email).strip().lower()


def _get_load_level(avg_meetings_per_week: float) -> str:
    if pd.isna(avg_meetings_per_week):
        return "Unknown"

    if avg_meetings_per_week >= 15:
        return "Very high"
    if avg_meetings_per_week >= 10:
        return "High"
    if avg_meetings_per_week >= 5:
        return "Moderate"

    return "Low"


def render(df: pd.DataFrame) -> None:
    st.header("Employee meeting load")

    if df.empty:
        st.warning("No employee meeting-load data available for the selected filters.")
        return

    required_columns = {
        "user_email",
        "week_start_date",
        "weekly_meetings",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        st.error(
            "The employee meeting-load section is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
        return

    load_df = df.copy()

    load_df["user_email"] = load_df["user_email"].apply(_format_employee_email)

    load_df["week_start_date"] = pd.to_datetime(
        load_df["week_start_date"],
        errors="coerce",
    )

    load_df["weekly_meetings"] = pd.to_numeric(
        load_df["weekly_meetings"],
        errors="coerce",
    ).fillna(0)

    optional_numeric_columns = [
        "total_meetings",
        "number_of_weeks",
        "avg_meetings_per_week",
        "max_meetings_in_week",
    ]

    for column in optional_numeric_columns:
        if column in load_df.columns:
            load_df[column] = pd.to_numeric(
                load_df[column],
                errors="coerce",
            )

    load_df = load_df.dropna(
        subset=[
            "user_email",
            "week_start_date",
        ]
    )

    if load_df.empty:
        st.warning("No valid employee meeting-load rows are available.")
        return

    # Recalculate these from the filtered dataframe so sidebar date filters
    # affect the KPIs and leaderboard correctly.
    employee_summary_df = (
        load_df
        .groupby("user_email", as_index=False)
        .agg(
            total_meetings=("weekly_meetings", "sum"),
            number_of_weeks=("week_start_date", "nunique"),
            avg_meetings_per_week=("weekly_meetings", "mean"),
            max_meetings_in_week=("weekly_meetings", "max"),
        )
    )

    employee_summary_df["avg_meetings_per_week"] = (
        employee_summary_df["avg_meetings_per_week"].round(2)
    )

    employee_summary_df["load_level"] = employee_summary_df[
        "avg_meetings_per_week"
    ].apply(_get_load_level)

    employee_summary_df = employee_summary_df.sort_values(
        [
            "avg_meetings_per_week",
            "total_meetings",
        ],
        ascending=[False, False],
    )

    total_meetings = int(load_df["weekly_meetings"].sum())
    active_employees = int(employee_summary_df["user_email"].nunique())

    avg_meetings_per_employee_week = (
        employee_summary_df["avg_meetings_per_week"].mean()
        if not employee_summary_df.empty
        else 0
    )

    highest_weekly_load = (
        int(load_df["weekly_meetings"].max())
        if not load_df.empty
        else 0
    )

    busiest_employee = (
        employee_summary_df.iloc[0]["user_email"]
        if not employee_summary_df.empty
        else "N/A"
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total meetings", f"{total_meetings:,}")
    col2.metric("Active employees", f"{active_employees:,}")
    col3.metric(
        "Avg meetings / employee / week",
        f"{avg_meetings_per_employee_week:,.2f}",
    )
    col4.metric("Highest weekly load", f"{highest_weekly_load:,}")

    st.caption(f"Busiest employee in the selected period: **{busiest_employee}**")

    st.subheader("Average meetings per week by employee")

    leaderboard_chart = (
        alt.Chart(employee_summary_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "avg_meetings_per_week:Q",
                title="Average meetings per week",
            ),
            y=alt.Y(
                "user_email:N",
                title="Employee",
                sort="-x",
            ),
            tooltip=[
                alt.Tooltip("user_email:N", title="Employee"),
                alt.Tooltip(
                    "avg_meetings_per_week:Q",
                    title="Avg meetings / week",
                    format=",.2f",
                ),
                alt.Tooltip(
                    "total_meetings:Q",
                    title="Total meetings",
                    format=",",
                ),
                alt.Tooltip(
                    "number_of_weeks:Q",
                    title="Weeks active",
                    format=",",
                ),
                alt.Tooltip(
                    "max_meetings_in_week:Q",
                    title="Max meetings in one week",
                    format=",",
                ),
                alt.Tooltip("load_level:N", title="Load level"),
            ],
        )
        .properties(height=max(300, min(650, active_employees * 35)))
    )

    st.altair_chart(leaderboard_chart, width="stretch")

    st.subheader("Weekly meeting load by employee")

    weekly_trend_df = (
        load_df
        .groupby(
            [
                "week_start_date",
                "user_email",
            ],
            as_index=False,
        )
        .agg(
            weekly_meetings=("weekly_meetings", "sum"),
        )
        .sort_values(["user_email", "week_start_date"])
    )

    weekly_trend_chart = (
        alt.Chart(weekly_trend_df)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "week_start_date:T",
                title="Week starting",
            ),
            y=alt.Y(
                "weekly_meetings:Q",
                title="Weekly meetings",
            ),
            color=alt.Color(
                "user_email:N",
                title="Employee",
            ),
            tooltip=[
                alt.Tooltip(
                    "week_start_date:T",
                    title="Week starting",
                    format="%Y-%m-%d",
                ),
                alt.Tooltip("user_email:N", title="Employee"),
                alt.Tooltip(
                    "weekly_meetings:Q",
                    title="Weekly meetings",
                    format=",",
                ),
            ],
        )
        .properties(height=375)
    )

    st.altair_chart(weekly_trend_chart, width="stretch")

    st.subheader("Employee / week load heatmap")

    heatmap_df = weekly_trend_df.copy()

    heatmap_df["week_label"] = heatmap_df["week_start_date"].dt.strftime(
        "%Y-%m-%d"
    )

    employee_order = (
        employee_summary_df
        .sort_values(
            [
                "avg_meetings_per_week",
                "total_meetings",
            ],
            ascending=[False, False],
        )["user_email"]
        .tolist()
    )

    heatmap_chart = (
        alt.Chart(heatmap_df)
        .mark_rect()
        .encode(
            x=alt.X(
                "week_label:N",
                title="Week starting",
                sort=sorted(heatmap_df["week_label"].unique()),
            ),
            y=alt.Y(
                "user_email:N",
                title="Employee",
                sort=employee_order,
            ),
            color=alt.Color(
                "weekly_meetings:Q",
                title="Meetings",
                scale=alt.Scale(scheme="oranges"),
            ),
            tooltip=[
                alt.Tooltip("user_email:N", title="Employee"),
                alt.Tooltip("week_label:N", title="Week starting"),
                alt.Tooltip(
                    "weekly_meetings:Q",
                    title="Meetings",
                    format=",",
                ),
            ],
        )
        .properties(height=max(300, min(650, active_employees * 35)))
    )

    heatmap_text = (
        alt.Chart(heatmap_df)
        .mark_text()
        .encode(
            x=alt.X(
                "week_label:N",
                sort=sorted(heatmap_df["week_label"].unique()),
            ),
            y=alt.Y(
                "user_email:N",
                sort=employee_order,
            ),
            text=alt.Text(
                "weekly_meetings:Q",
                format=",",
            ),
        )
    )

    st.altair_chart(heatmap_chart + heatmap_text, width="stretch")

    st.subheader("Load level summary")

    load_level_df = (
        employee_summary_df
        .groupby("load_level", as_index=False)
        .agg(
            employee_count=("user_email", "nunique"),
            total_meetings=("total_meetings", "sum"),
            avg_meetings_per_week=("avg_meetings_per_week", "mean"),
        )
    )

    load_level_order = [
        "Very high",
        "High",
        "Moderate",
        "Low",
        "Unknown",
    ]

    load_level_df["avg_meetings_per_week"] = (
        load_level_df["avg_meetings_per_week"].round(2)
    )

    load_level_chart = (
        alt.Chart(load_level_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "load_level:N",
                title="Load level",
                sort=load_level_order,
            ),
            y=alt.Y(
                "employee_count:Q",
                title="Employees",
            ),
            tooltip=[
                alt.Tooltip("load_level:N", title="Load level"),
                alt.Tooltip(
                    "employee_count:Q",
                    title="Employees",
                    format=",",
                ),
                alt.Tooltip(
                    "total_meetings:Q",
                    title="Total meetings",
                    format=",",
                ),
                alt.Tooltip(
                    "avg_meetings_per_week:Q",
                    title="Avg meetings / week",
                    format=",.2f",
                ),
            ],
        )
        .properties(height=300)
    )

    st.altair_chart(load_level_chart, width="stretch")

    with st.expander("Employee meeting-load leaderboard"):
        display_df = employee_summary_df.copy()

        display_df = display_df.rename(
            columns={
                "user_email": "Employee",
                "total_meetings": "Total Meetings",
                "number_of_weeks": "Weeks Active",
                "avg_meetings_per_week": "Avg Meetings / Week",
                "max_meetings_in_week": "Max Meetings In One Week",
                "load_level": "Load Level",
            }
        )

        st.dataframe(
            display_df[
                [
                    "Employee",
                    "Total Meetings",
                    "Weeks Active",
                    "Avg Meetings / Week",
                    "Max Meetings In One Week",
                    "Load Level",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

    with st.expander("Weekly employee meeting-load detail"):
        display_df = weekly_trend_df.copy()

        display_df = display_df.rename(
            columns={
                "week_start_date": "Week Starting",
                "user_email": "Employee",
                "weekly_meetings": "Weekly Meetings",
            }
        )

        st.dataframe(
            display_df[
                [
                    "Week Starting",
                    "Employee",
                    "Weekly Meetings",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

    with st.expander("Raw employee meeting-load data"):
        display_df = load_df.copy()

        display_df = display_df.rename(
            columns={
                "user_email": "Employee",
                "week_start_date": "Week Starting",
                "weekly_meetings": "Weekly Meetings",
                "total_meetings": "Total Meetings",
                "number_of_weeks": "Weeks Active",
                "avg_meetings_per_week": "Avg Meetings / Week",
                "max_meetings_in_week": "Max Meetings In One Week",
                "first_booking_date_in_week": "First Booking Date In Week",
                "last_booking_date_in_week": "Last Booking Date In Week",
            }
        )

        preferred_columns = [
            "Employee",
            "Week Starting",
            "Weekly Meetings",
            "Total Meetings",
            "Weeks Active",
            "Avg Meetings / Week",
            "Max Meetings In One Week",
            "First Booking Date In Week",
            "Last Booking Date In Week",
        ]

        columns_to_show = [
            column
            for column in preferred_columns
            if column in display_df.columns
        ]

        st.dataframe(
            display_df[columns_to_show],
            width="stretch",
            hide_index=True,
        )