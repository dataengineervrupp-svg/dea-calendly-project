from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    current_timestamp,
    input_file_name,
    regexp_extract,
    to_timestamp,
    regexp_replace,
    lower
)
from pathlib import Path
import argparse

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-path", required=True)
    parser.add_argument("--silver-path", required=True)
    parser.add_argument("--location", action="store_true")
    return parser.parse_args()

def main():
    args = parse_args()
    RAW_PATH = args.raw_path
    SILVER_PATH = args.silver_path
    run_location = args.location
    print(args)
    if run_location:
        spark = (
            SparkSession.builder
            .appName("calendly_webhooks_to_silver")
            .getOrCreate()
        )
        print('run_location exists, running local version')
    else:
        spark = (
            SparkSession.builder
            .appName("calendly_webhooks_to_silver")
            .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
            .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
            .getOrCreate()
        )
        print(f'no run_location, preparing to save to {SILVER_PATH}')

    if run_location:
        json_files = [
            str(p.resolve()).replace("\\", "/")
            for p in Path(RAW_PATH).glob("*.json")
        ]
    
    df_raw = (
        spark.read
        .option("multiLine", "true")
        .option("recursiveFileLookup", "true")
        .json(json_files if run_location else RAW_PATH)
    )
    print('raw table rows:', df_raw.count())

    # df_raw.printSchema()
    # df_raw.show(truncate=False)

    # df_raw.select(
    #     col("event").alias("webhook_event_type"),
    #     col("payload.event").alias("payload_event"),
    #     col("payload.uri").alias("invitee_uri")
    # ).show(truncate=False)

    df_silver = (
        df_raw
        .withColumn("raw_file_path", input_file_name())
        .withColumn("processed_at", current_timestamp())

        # Top-level webhook metadata
        .withColumn("webhook_event_type", col("event"))
        .withColumn(
            "webhook_created_at",
            to_timestamp(
                regexp_replace(col("created_at"), r"\s+", ""),
                "yyyy-MM-dd'T'HH:mm:ss.SSSSSS'Z'"
            )
        )
        .withColumn("webhook_created_by", col("created_by"))

        # Scheduled event fields
        .withColumn("event_uri", col("payload.event"))
        .withColumn(
            "event_id",
            regexp_extract(col("payload.event"), r"/scheduled_events/([^/?]+)", 1)
        )
        .withColumn("event_start_time", to_timestamp(col("payload.scheduled_event.start_time")))
        .withColumn("event_end_time", to_timestamp(col("payload.scheduled_event.end_time")))
        .withColumn("event_name", col("payload.scheduled_event.name"))
        .withColumn("event_status", col("payload.scheduled_event.status"))
        .withColumn(
            "event_type_code",
            regexp_extract(col("payload.scheduled_event.event_type"), r"/event_types/([^/?]+)", 1)
        )

        # Invitee Fields
        .withColumn("invitee_email", col("payload.email"))
        .withColumn("invitee_first_name", col("payload.first_name"))
        .withColumn("invitee_last_name", col("payload.last_name"))
        .withColumn("invitee_name", col("payload.name"))
        .withColumn("invitee_name_safe", lower(regexp_replace(col("invitee_name"), r"\s+", "_")))

        # Tracking / attribution fields
        .withColumn("tracking_utm_source", col("payload.tracking.utm_source"))
        .withColumn("tracking_utm_medium", col("payload.tracking.utm_medium"))
        .withColumn("tracking_utm_campaign", col("payload.tracking.utm_campaign"))
        .withColumn("tracking_utm_content", col("payload.tracking.utm_content"))
        .withColumn("tracking_utm_term", col("payload.tracking.utm_term"))

        # Select clean silver columns
        .select(
            "event_id",
            "event_uri",
            "webhook_event_type",
            "webhook_created_at",
            "event_name",
            "event_status",
            "event_start_time",
            "event_end_time",
            "event_type_code",
            "invitee_email",
            "invitee_name",
            "invitee_name_safe",
            "invitee_first_name",
            "invitee_last_name",
            "tracking_utm_source",
            "tracking_utm_medium",
            "tracking_utm_campaign",
            "tracking_utm_content",
            "tracking_utm_term",
            "raw_file_path",
            "processed_at",
        )
        .dropDuplicates(["event_id", "invitee_name", "webhook_event_type"])
    )

    if run_location:
        print('local run - no silver data saved. showing partial table')
        df_silver.select(
            col('event_id'),
            col("invitee_name_safe"),
            col("event_type_code")
        ).show(truncate=False)
    else:
        (
            df_silver.write
            .mode("overwrite")
            .parquet(SILVER_PATH)
        )
        print(f'silver data saved to {SILVER_PATH}')
    # df_silver.printSchema()
    # df_silver.show(truncate=False)
    
    

    # df_silver.groupby('webhook_event_type').count().show(truncate=False)

    print('silver table rows:', df_silver.count())

if __name__ == "__main__":
    main()