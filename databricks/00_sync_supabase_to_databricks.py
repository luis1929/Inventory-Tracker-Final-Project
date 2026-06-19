# Databricks notebook source
# MAGIC %md
# MAGIC # Sincronización Supabase → Databricks
# MAGIC
# MAGIC Ejecutar diariamente vía Workflows (Job schedule).
# MAGIC Lee todas las tablas desde Supabase REST API y sobreescribe en Databricks.

# COMMAND ----------

import requests
import pandas as pd
from pyspark.sql.types import DecimalType

SUPABASE_URL = "https://uapulmxutzezodmxavdd.supabase.co"
API_KEY = dbutils.secrets.get("supabase", "service_key")
HEADERS = {"apikey": API_KEY, "Authorization": f"Bearer {API_KEY}"}

tables = [
    ("ingredient_table",       "name"),
    ("menu_board",             "id"),
    ("menu_recipe_items",      "id"),
    ("sales_projections",      "id"),
    ("nutrition_table",        "id"),
    ("daily_sales",            "id"),
    ("sale_items",             "id"),
    ("user_profiles",          "id"),
]

DECIMAL_COLS = [
    "count", "cost", "min_stock", "unit_cost", "total_dish_cost",
    "estimated_qty", "estimated_cost", "sale_price", "cost_total",
    "overhead_cost", "total_sale", "total_cost", "total_profit",
    "line_sale", "line_cost", "line_profit", "sale_price_unit",
    "cost_per_unit", "protein_g", "fat_g", "carbs_g", "fiber_g",
    "sodium_mg", "calories", "calories_usda", "calories_protein",
    "calories_fat", "calories_carbs", "total_calories",
    "total_calories_no_fiber", "quantity_grams", "portion_weight_g",
]

for table, order_col in tables:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=HEADERS,
        params={"order": f"{order_col}.asc", "limit": 10000}
    )
    df = pd.DataFrame(r.json())
    df = df.where(pd.notna(df), None)
    spark_df = spark.createDataFrame(df)
    for c in DECIMAL_COLS:
        if c in spark_df.columns:
            spark_df = spark_df.withColumn(c, spark_df[c].cast(DecimalType(12,2)))
    spark_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)
    print(f"{table}: {len(df)} rows")

# COMMAND ----------

print("Sync completado:", datetime.now())
