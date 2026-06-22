import argparse

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    count,
    current_timestamp,
    date_format,
    date_trunc,
    dayofweek,
    lit,
    round as spark_round,
    sum as spark_sum,
    to_date,
    when,
)
from pyspark.sql.types import DecimalType


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
        help="S3 path for gold daily channel performance Delta table.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    spark = (
        SparkSession.builder
        .appName("gold-daily-channel-performance")
        .getOrCreate()
    )

    # set manually for testing, but overwrite below with actual args
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
        "gold/daily_channel_performance_delta/"
    )
    webhooks_silver_path = args.webhooks_silver_path.rstrip("/")
    marketing_silver_path = args.marketing_silver_path.rstrip("/")
    gold_path = args.gold_path.rstrip("/")
    print('paths set successfully')
    webhooks_df = (
        spark.read
        .format("delta")
        .load(webhooks_silver_path)
    )
    
    marketing_df = (
        spark.read
        .format("parquet")
        .load(marketing_silver_path)
    )
    marketing_df = marketing_df.filter(col("spend_date") >= lit("2026-06-09").cast("date"))
    marketing_df = marketing_df.drop_duplicates()
    
    dates_table = (
        marketing_df
        .filter(col("spend_date") >= lit("2026-06-09").cast("date"))
        .select('spend_date').groupby('spend_date').count().sort('spend_date', ascending=True)
    )
    print('dataframes read successfully')
    print('lowest marketing_df dates:')
    dates_table.show(5, truncate=False)
    
    # Bookings by date + channel/event type.
    # The marketing silver table maps channel -> webhook_event_type,
    # so webhook_event_type is the join key.
    bookings_daily = (
        webhooks_df
        .withColumn(
            "booking_date",
            to_date(col("webhook_created_at")),
        )
        .filter(col("booking_date").isNotNull())
        .filter(col("event_type_code").isNotNull())
        .groupBy(
            "booking_date",
            "event_type_code",
        )
        .agg(
            count(lit(1)).alias("bookings_count"),
        )
    )
    booking_dates_table = (
        bookings_daily
        .select('booking_date').groupby('booking_date').count()
        .sort('booking_date', ascending=True)
    )
    print('booking dates mins:')
    booking_dates_table.show(5, truncate=False)

    # Spend by date + channel/event type.
    # In theory silver marketing is already one row per spend_date/channel,
    # but grouping here makes this robust if duplicate rows sneak in.
    spend_daily = (
        marketing_df
        .filter(col("spend_date").isNotNull())
        .filter(col("channel").isNotNull())
        .filter(col("event_type_code").isNotNull())
        .groupBy(
            "spend_date",
            "channel",
            "event_type_code",
        )
        .agg(
            spark_sum(col("spend")).alias("marketing_spend"),
        )
    )

    # Full outer join keeps:
    # - spend days with zero bookings
    # - booking days with missing spend
    gold_df = (
        spend_daily.alias("spend")
        .join(
            bookings_daily.alias("bookings"),
            (
                col("spend.spend_date") == col("bookings.booking_date")
            )
            & (
                col("spend.event_type_code")
                == col("bookings.event_type_code")
            ),
            how="full_outer",
        )
        .select(
            when(
                col("bookings.booking_date").isNotNull(),
                col("bookings.booking_date"),
            )
            .otherwise(col("spend.spend_date"))
            .alias("performance_date"),

            col("spend.channel").alias("channel"),

            when(
                col("bookings.event_type_code").isNotNull(),
                col("bookings.event_type_code"),
            )
            .otherwise(col("spend.event_type_code"))
            .alias("event_type_code"),

            when(
                col("bookings.bookings_count").isNotNull(),
                col("bookings.bookings_count"),
            )
            .otherwise(lit(0))
            .alias("bookings_count"),

            when(
                col("spend.marketing_spend").isNotNull(),
                col("spend.marketing_spend"),
            )
            .otherwise(lit(0))
            .cast(DecimalType(12, 2))
            .alias("marketing_spend"),
        )
        .withColumn(
            "cost_per_booking",
            when(
                col("bookings_count") > 0,
                spark_round(
                    col("marketing_spend") / col("bookings_count"),
                    2,
                ),
            )
            .otherwise(None)
            .cast(DecimalType(12, 2)),
        )
        .withColumn(
            "day_of_week_number",
            dayofweek(col("performance_date")),
        )
        .withColumn(
            "day_of_week_name",
            date_format(col("performance_date"), "EEEE"),
        )
        .withColumn(
            "week_start_date",
            to_date(date_trunc("week", col("performance_date"))),
        )
        .withColumn(
            "month_start_date",
            to_date(date_trunc("month", col("performance_date"))),
        )
        .withColumn(
            "processed_at",
            current_timestamp(),
        )
        .select(
            "performance_date",
            "day_of_week_number",
            "day_of_week_name",
            "week_start_date",
            "month_start_date",
            "channel",
            "event_type_code",
            "bookings_count",
            "marketing_spend",
            "cost_per_booking",
            "processed_at",
        )
    )

    print("Bookings daily row count:", bookings_daily.count())
    print("Spend daily row count:", spend_daily.count())
    print("Gold row count:", gold_df.count())

    gold_df.orderBy(
        col("performance_date"),
        col("channel"),
    ).show(5, truncate=False)

    (
        gold_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .save(gold_path)
    )
    print(f"Wrote gold table to {gold_path}")

    dashboard_export_path = "s3://calendly-project-467875655273-us-east-1-an/gold/dashboard_exports/daily_channel_performance/"
    (
        gold_df.write
        .mode("overwrite")
        .parquet(dashboard_export_path)
    )
    print(f"Wrote parquet table to {dashboard_export_path}")


    spark.stop()


if __name__ == "__main__":
    main()