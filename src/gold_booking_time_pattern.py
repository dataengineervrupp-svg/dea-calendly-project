import argparse

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    count,
    current_timestamp,
    date_format,
    date_trunc,
    dayofweek,
    hour,
    lit,
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
        "--marketing-silver-path",
        required=True,
        help="S3 path to silver marketing spend Delta table.",
    )

    parser.add_argument(
        "--gold-path",
        required=True,
        help="S3 path for gold booking time patterns Delta table.",
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
        .appName("gold-booking-time-patterns")
        .getOrCreate()
    )

    
    webhooks_silver_path = (
        "s3://calendly-project-467875655273-us-east-1-an/"
        "silver/webhooks_delta/"
    )

    marketing_silver_path = (
        "s3://calendly-project-467875655273-us-east-1-an/"
        "silver/marketing_spend_delta/"
    )

    gold_path = (
        "s3://calendly-project-467875655273-us-east-1-an/"
        "gold/booking_time_patterns_delta/"
    )

    dashboard_export_path = (
        "s3://calendly-project-467875655273-us-east-1-an/"
        "gold/dashboard_exports/booking_time_patterns/"
    )
    webhooks_silver_path = webhooks_silver_path.rstrip("/")
    marketing_silver_path = marketing_silver_path.rstrip("/")
    gold_path = gold_path.rstrip("/")
    dashboard_export_path = dashboard_export_path.rstrip("/")
    
    webhooks_silver_path = args.webhooks_silver_path.rstrip("/")
    marketing_silver_path = args.marketing_silver_path.rstrip("/")
    gold_path = args.gold_path.rstrip("/")
    dashboard_export_path = args.dashboard_export_path.rstrip("/")

    webhooks_df = (
        spark.read
        .format("delta")
        .load(webhooks_silver_path)
    )

    marketing_df = (
        spark.read
        .format("delta")
        .load(marketing_silver_path)
    )

    # Build a clean event type -> channel mapping.
    # Marketing spend has many rows per channel/date, so dedupe it first.
    channel_mapping_df = (
        marketing_df
        .select(
            col("event_type_code"),
            col("channel"),
        )
        .filter(col("event_type_code").isNotNull())
        .filter(col("channel").isNotNull())
        .dropDuplicates(["event_type_code"])
    )

    bookings_df = (
        webhooks_df
        .filter(col("webhook_created_at").isNotNull())
        .filter(col("event_type_code").isNotNull())
        .withColumn(
            "booking_date",
            to_date(col("webhook_created_at")),
        )
        .withColumn(
            "hour_of_day",
            hour(col("webhook_created_at")),
        )
        .withColumn(
            "day_of_week_number",
            dayofweek(col("webhook_created_at")),
        )
        .withColumn(
            "day_of_week_name",
            date_format(col("webhook_created_at"), "EEEE"),
        )
        .withColumn(
            "week_start_date",
            to_date(date_trunc("week", col("webhook_created_at"))),
        )
        .withColumn(
            "month_start_date",
            to_date(date_trunc("month", col("webhook_created_at"))),
        )
    )

    bookings_with_channel_df = (
        bookings_df.alias("bookings")
        .join(
            channel_mapping_df.alias("channels"),
            col("bookings.event_type_code")
            == col("channels.event_type_code"),
            how="left",
        )
        .select(
            col("bookings.booking_date"),
            col("bookings.week_start_date"),
            col("bookings.month_start_date"),
            col("bookings.day_of_week_number"),
            col("bookings.day_of_week_name"),
            col("bookings.hour_of_day"),
            col("bookings.event_type_code"),
            col("channels.channel"),
        )
        .withColumn(
            "channel",
            when(col("channel").isNotNull(), col("channel"))
            .otherwise(lit("unknown")),
        )
    )

    gold_df = (
        bookings_with_channel_df
        .withColumn(
            "time_slot",
            when(
                (col("hour_of_day") >= 0) & (col("hour_of_day") <= 5),
                lit("overnight"),
            )
            .when(
                (col("hour_of_day") >= 6) & (col("hour_of_day") <= 8),
                lit("early_morning"),
            )
            .when(
                (col("hour_of_day") >= 9) & (col("hour_of_day") <= 11),
                lit("morning"),
            )
            .when(
                (col("hour_of_day") >= 12) & (col("hour_of_day") <= 16),
                lit("afternoon"),
            )
            .when(
                (col("hour_of_day") >= 17) & (col("hour_of_day") <= 20),
                lit("evening"),
            )
            .otherwise(lit("late_evening")),
        )
        .withColumn(
            "time_slot_sort",
            when(col("time_slot") == "overnight", lit(1))
            .when(col("time_slot") == "early_morning", lit(2))
            .when(col("time_slot") == "morning", lit(3))
            .when(col("time_slot") == "afternoon", lit(4))
            .when(col("time_slot") == "evening", lit(5))
            .when(col("time_slot") == "late_evening", lit(6))
            .otherwise(lit(99)),
        )
        .groupBy(
            "booking_date",
            "week_start_date",
            "month_start_date",
            "day_of_week_number",
            "day_of_week_name",
            "hour_of_day",
            "time_slot",
            "time_slot_sort",
            "channel",
            "event_type_code",
        )
        .agg(
            count(lit(1)).alias("bookings_count"),
        )
        .withColumn(
            "processed_at",
            current_timestamp(),
        )
        .select(
            "booking_date",
            "week_start_date",
            "month_start_date",
            "day_of_week_number",
            "day_of_week_name",
            "hour_of_day",
            "time_slot",
            "time_slot_sort",
            "channel",
            "event_type_code",
            "bookings_count",
            "processed_at",
        )
    )

    print("Gold booking time patterns row count:", gold_df.count())

    gold_df.orderBy(
        col("booking_date").desc(),
        col("day_of_week_number"),
        col("hour_of_day"),
        col("channel"),
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