from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .appName("calendly_raw_load_test")
    .getOrCreate()
)

RAW_PATH = "data/webhooks/real_webhook.json"


df_raw = (
    spark.read
    .option("multiLine", "true")
    .json(RAW_PATH)
)

df_raw.printSchema()
df_raw.show(truncate=False)