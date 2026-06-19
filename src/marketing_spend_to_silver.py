import argparse

from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import (
    col,
    current_timestamp,
    input_file_name,
    lower,
    regexp_replace,
    row_number,
    round as spark_round,
    to_date,
    trim,
)
from pyspark.sql.types import DecimalType


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--raw-path",
        required=True,
        help="S3 path containing raw marketing-spend JSON files.",
    )

    parser.add_argument(
        "--silver-path",
        required=True,
        help="S3 path for the silver Delta table.",
    )

    return parser.parse_args()


def delta_table_exists(spark: SparkSession, path: str) -> bool:
    """Return True when the target path contains a Delta transaction log."""

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

    spark = (
        SparkSession.builder
        .appName("marketing-spend-to-silver")
        .getOrCreate()
    )

    raw_path = args.raw_path.rstrip("/") + "/"
    silver_path = args.silver_path.rstrip("/")

    # multiLine=True supports JSON files containing an array of objects.
    df_raw = (
        spark.read
        .option("multiLine", "true")
        .json(raw_path)
        .withColumn("raw_file_path", input_file_name())
        .withColumn(
            "raw_file_modified_at",
            col("_metadata.file_modification_time"),
        )
    )

    df_clean = (
        df_raw
        .withColumn("spend_date", to_date(col("date"), "yyyy-MM-dd"))
        .withColumn(
            "channel",
            regexp_replace(
                lower(trim(col("channel"))),
                r"\s+",
                "_",
            ),
        )
        .withColumn(
            "spend",
            spark_round(
                col("spend").cast(DecimalType(12, 2)),
                2,
            ),
        )
        .withColumn("processed_at", current_timestamp())
        .select(
            "spend_date",
            "channel",
            "spend",
            "raw_file_path",
            "raw_file_modified_at",
            "processed_at",
        )
        .filter(col("spend_date").isNotNull())
        .filter(col("channel").isNotNull())
        .filter(col("spend").isNotNull())
    )

    # Each daily file contains a rolling 30-day snapshot.
    # Keep the row from the newest source file for each date/channel.
    latest_record_window = (
        Window
        .partitionBy("spend_date", "channel")
        .orderBy(
            col("raw_file_modified_at").desc_nulls_last(),
            col("raw_file_path").desc(),
        )
    )

    df_silver = (
        df_clean
        .withColumn(
            "_record_rank",
            row_number().over(latest_record_window),
        )
        .filter(col("_record_rank") == 1)
        .drop("_record_rank")
    )

    print("Raw row count:", df_raw.count())
    print("Deduplicated silver row count:", df_silver.count())

    df_silver.orderBy(
        col("spend_date").desc(),
        col("channel"),
    ).show(50, truncate=False)

    if not delta_table_exists(spark, silver_path):
        print(f"Creating Delta table at {silver_path}")

        (
            df_silver.write
            .format("delta")
            .mode("overwrite")
            .save(silver_path)
        )

    else:
        print(f"Merging into Delta table at {silver_path}")

        df_silver.createOrReplaceTempView(
            "marketing_spend_updates"
        )

        spark.sql(
            f"""
            MERGE INTO delta.`{silver_path}` AS target
            USING marketing_spend_updates AS source
              ON target.spend_date = source.spend_date
             AND target.channel = source.channel

            WHEN MATCHED
              AND (
                    target.spend <> source.spend
                 OR target.raw_file_modified_at
                    < source.raw_file_modified_at
              )
            THEN UPDATE SET *

            WHEN NOT MATCHED
            THEN INSERT *
            """
        )

    final_df = (
        spark.read
        .format("delta")
        .load(silver_path)
    )

    print("Final Delta row count:", final_df.count())

    spark.stop()


if __name__ == "__main__":
    main()