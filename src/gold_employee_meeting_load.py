import argparse

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    avg,
    col,
    count,
    countDistinct,
    current_timestamp,
    date_trunc,
    lit,
    max as spark_max,
    min as spark_min,
    round as spark_round,
    sum as spark_sum,
    to_date,
    when,
)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--webhooks-silver-path",
        required=True,
        help="S3 path to silver webhook Delta table.",
    )

    parser.add_argument(
        "--gold-path",
        required=True,
        help="S3 path for gold employee meeting load Delta table.",
    )

    parser.add_argument(
        "--dashboard-export-path",
        required=True,
        help="S3 path for dashboard-friendly Parquet export.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    spark = (
        SparkSession.builder
        .appName("gold-employee-meeting-load")
        .getOrCreate()
    )
    webhooks_silver_path = (
        "s3://calendly-project-467875655273-us-east-1-an/"
        "silver/webhooks_delta/"
    )

    gold_path = (
        "s3://calendly-project-467875655273-us-east-1-an/"
        "gold/employee_meeting_load_delta/"
    )

    dashboard_export_path = (
        "s3://calendly-project-467875655273-us-east-1-an/"
        "gold/dashboard_exports/employee_meeting_load/"
    )
    
    webhooks_silver_path = webhooks_silver_path.rstrip("/")
    gold_path = gold_path.rstrip("/")
    dashboard_export_path = dashboard_export_path.rstrip("/")
    webhooks_silver_path = args.webhooks_silver_path.rstrip("/")
    gold_path = args.gold_path.rstrip("/")
    dashboard_export_path = args.dashboard_export_path.rstrip("/")

    webhooks_df = (
        spark.read
        .format("delta")
        .load(webhooks_silver_path)
    )

    # This assumes silver webhooks has user_email.
    # If your actual employee column has a different name, change it here.
    meetings_df = (
        webhooks_df
        .filter(col("webhook_created_at").isNotNull())
        .filter(col("user_email").isNotNull())
        .withColumn(
            "booking_date",
            to_date(col("webhook_created_at")),
        )
        .withColumn(
            "week_start_date",
            to_date(date_trunc("week", col("webhook_created_at"))),
        )
        .select(
            "user_email",
            "booking_date",
            "week_start_date",
            "webhook_key",
            "event_id",
            "event_type_code",
        )
    )

    # Prefer counting webhook_key if present because it should identify unique bookings.
    # If webhook_key is null, fall back to event_id.
    meetings_df = meetings_df.withColumn(
        "meeting_key",
        when(col("webhook_key").isNotNull(), col("webhook_key"))
        .when(col("event_id").isNotNull(), col("event_id"))
        .otherwise(lit(None)),
    )

    weekly_load_df = (
        meetings_df
        .groupBy(
            "user_email",
            "week_start_date",
        )
        .agg(
            countDistinct("meeting_key").alias("weekly_meetings"),
            spark_min("booking_date").alias("first_booking_date_in_week"),
            spark_max("booking_date").alias("last_booking_date_in_week"),
        )
    )

    employee_summary_df = (
        weekly_load_df
        .groupBy("user_email")
        .agg(
            countDistinct("week_start_date").alias("number_of_weeks"),
            spark_sum("weekly_meetings").alias("total_meetings"),
            avg("weekly_meetings").alias("avg_meetings_per_week"),
            spark_max("weekly_meetings").alias("max_meetings_in_week"),
        )
    )

    gold_df = (
        weekly_load_df.alias("weekly")
        .join(
            employee_summary_df.alias("summary"),
            on="user_email",
            how="left",
        )
        .select(
            col("weekly.user_email"),
            col("weekly.week_start_date"),
            col("weekly.weekly_meetings"),
            col("summary.total_meetings"),
            col("summary.number_of_weeks"),
            spark_round(
                col("summary.avg_meetings_per_week"),
                2,
            ).alias("avg_meetings_per_week"),
            col("summary.max_meetings_in_week"),
            col("weekly.first_booking_date_in_week"),
            col("weekly.last_booking_date_in_week"),
        )
        .withColumn(
            "processed_at",
            current_timestamp(),
        )
    )

    print("Employee meeting load row count:", gold_df.count())

    gold_df.orderBy(
        col("week_start_date").desc(),
        col("weekly_meetings").desc(),
        col("user_email"),
    ).show(5, truncate=False)

    (
        gold_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(gold_path)
    )

    (
        gold_df.write
        .mode("overwrite")
        .parquet(dashboard_export_path)
    )

    print(f"Wrote Delta gold table to {gold_path}")
    print(f"Wrote dashboard Parquet export to {dashboard_export_path}")

    spark.stop()


if __name__ == "__main__":
    main()