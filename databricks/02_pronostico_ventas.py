# Databricks notebook source
# MAGIC %md
# MAGIC # Pronóstico de Ventas por Plato
# MAGIC Predice unidades a vender basado en historial de ventas.

# COMMAND ----------

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum as _sum, count, date_trunc, to_date
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.regression import RandomForestRegressor
import pandas as pd
import datetime

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TEMP VIEW ventas_plato AS
# MAGIC SELECT s.created_at, i.dish_id, i.dish_name, i.quantity
# MAGIC FROM daily_sales s
# MAGIC JOIN sale_items i ON s.id = i.sale_id
# MAGIC WHERE s.created_at >= '2026-05-01';

# COMMAND ----------

df = spark.sql("""
  SELECT dish_id, dish_name,
         DATE(created_at) AS dia,
         SUM(quantity) AS unidades
  FROM ventas_plato
  GROUP BY dish_id, dish_name, DATE(created_at)
  ORDER BY dish_id, dia
""")
display(df)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Exportar proyecciones calculadas a Supabase
# MAGIC
# MAGIC Después de generar pronósticos, puedes actualizar `sales_projections` vía API:
# MAGIC
# MAGIC ```python
# MAGIC import requests, json
# MAGIC
# MAGIC for row in predicciones.collect():
# MAGIC     requests.patch(
# MAGIC         f"{SUPABASE_URL}/rest/v1/sales_projections",
# MAGIC         headers=HEADERS,
# MAGIC         params={"dish_id": f"eq.{row.dish_id}"},
# MAGIC         json={"projected_units": int(row.prediccion)}
# MAGIC     )
# MAGIC ```
