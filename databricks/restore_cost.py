# Databricks notebook source
# MAGIC %md
# MAGIC # Restaurar cost original desde Delta table → Supabase

# COMMAND ----------

import requests
from pyspark.sql.types import DecimalType

SUPABASE_URL = "https://uapulmxutzezodmxavdd.supabase.co"
API_KEY = dbutils.secrets.get("supabase", "service_key")
HEADERS = {"apikey": API_KEY, "Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Leer datos originales de la Delta table
df = spark.sql("SELECT name, cost AS original_cost FROM default.ingredient_table ORDER BY name ASC")
rows = df.collect()
print(f"Registros en Delta: {len(rows)}")

# Restaurar cada cost en Supabase
updated = 0
for row in rows:
    name = row['name']
    cost = float(row['original_cost'])
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/ingredient_table",
        headers=HEADERS,
        json={'cost': cost},
        params={'name': f'eq.{name}'}
    )
    if r.status_code in (200, 204):
        updated += 1

print(f"✅ {updated} costs restaurados en Supabase")
