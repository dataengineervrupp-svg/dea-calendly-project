from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import (
    col,
    coalesce,
    concat_ws,
    current_timestamp,
    input_file_name,
    lit,
    lower,
    regexp_extract,
    regexp_replace,
    row_number,
    sha2,
    to_timestamp,
    trim,
)
from pathlib import Path
import argparse

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-path", required=True)
    parser.add_argument("--silver-path", required=True)
    parser.add_argument("--location", action="store_true")
    # parser.add_argument("--write_mode", default="overwrite", required=False)
    return parser.parse_args()

def delta_table_exists(spark: SparkSession, path: str) -> bool:
    """Return True when the path contains a Delta transaction log."""
    jvm = spark._jvm
    hadoop_conf = spark._jsc.hadoopConfiguration()
    filesystem = jvm.org.apache.hadoop.fs.FileSystem.get(
        jvm.java.net.URI.create(path),
        hadoop_conf,
    )
    delta_log_path = jvm.org.apache.hadoop.fs.Path(
        f"{path.rstrip('/')}/_delta_log"
    )
    return filesystem.exists(delta_log_path)

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
        .withColumn("user_email", col("payload.scheduled_event.event_memberships")[0].user_email)
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
            "user_email",
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
        # .dropDuplicates(["event_id", "invitee_name", "webhook_event_type"])
    )

    # add unique key for each json file
    df_silver = (
        df_silver
        .withColumn(
            "invitee_identity",
            coalesce(
                lower(trim(col("invitee_email"))),
                lower(trim(col("invitee_name_safe"))),
                lit("unknown"),
            )
        )
        .withColumn(
            "webhook_key",
            sha2(
                concat_ws(
                    "||",
                    col("event_id"),
                    col("webhook_event_type"),
                    col("invitee_identity"),
                ),
                256,
            )
        )
    )
    # de-duplicate logic using most recent records
    source_window = (
        Window
        .partitionBy("webhook_key")
        .orderBy(
            col("webhook_created_at").desc_nulls_last(),
            col("processed_at").desc(),
        )
    )

    df_silver = (
        df_silver
        .withColumn("_source_rank", row_number().over(source_window))
        .filter(col("_source_rank") == 1)
        .drop("_source_rank")
    )

    if run_location:
        print('local run - no silver data saved. showing partial table')
        df_silver.select(
            col('user_email'),
            col('event_id'),
            col("invitee_name_safe"),
            col("event_type_code"),
            # col("invitee_identity"),
            # col("webhook_key")
        ).show(truncate=False)
    else:

        if not delta_table_exists(spark, SILVER_PATH):
            print(f"Creating new Delta table at {SILVER_PATH}")
            (
                df_silver.write
                .format("delta")
                .mode("overwrite")
                .save(SILVER_PATH)
            )
        else:
            print(f"Merging records into existing Delta table at {SILVER_PATH}")
            df_silver.createOrReplaceTempView("calendly_webhook_updates")
            spark.sql(
                f"""
                MERGE INTO delta.`{SILVER_PATH}` AS target
                USING calendly_webhook_updates AS source
                ON target.webhook_key = source.webhook_key
                WHEN MATCHED THEN UPDATE SET *
                WHEN NOT MATCHED THEN INSERT *
                """
            )
            print(f'silver data saved to {SILVER_PATH}')
            print(
                "Silver Delta row count:",
                spark.read.format("delta").load(SILVER_PATH).count(),
            )
    # df_silver.printSchema()
    # df_silver.show(truncate=False)
    
    # df_silver.groupby('webhook_event_type').count().show(truncate=False)
    print('silver table rows:', df_silver.count())
    spark.stop()

if __name__ == "__main__":
    main()