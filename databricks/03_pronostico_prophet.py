# Databricks notebook source
# MAGIC %md
# MAGIC # Pronóstico Prophet → Sales Projections
# MAGIC
# MAGIC Lee ventas históricas, entrena Prophet por plato, escribe las unidades proyectadas en `sales_projections` (Supabase).

# COMMAND ----------

import requests
import pandas as pd
from prophet import Prophet
from datetime import datetime, timedelta
import numpy as np

SUPABASE_URL = "https://uapulmxutzezodmxavdd.supabase.co"
API_KEY = dbutils.secrets.get("supabase", "service_key")
HEADERS = {"apikey": API_KEY, "Authorization": f"Bearer {API_KEY}"}

# COMMAND ----------

# 1. Cargar ventas históricas
df = spark.sql("""
  SELECT i.dish_id, i.dish_name,
         DATE(s.created_at) AS dia,
         SUM(i.quantity) AS unidades
  FROM daily_sales s
  JOIN sale_items i ON s.id = i.sale_id
  WHERE s.created_at >= '2026-05-01'
  GROUP BY i.dish_id, i.dish_name, DATE(s.created_at)
  ORDER BY i.dish_id, dia
""").toPandas()

print(f"Ventas cargadas: {len(df)} registros, {df['dish_id'].nunique()} platos")

# COMMAND ----------

# 2. Cargar proyecciones actuales de Supabase (para mantener dish_id sin ventas)
r = requests.get(f"{SUPABASE_URL}/rest/v1/sales_projections", headers=HEADERS,
                 params={"select": "id,dish_id,dish_name,projected_units"})
current_projs = {p['dish_id']: p for p in r.json()}
print(f"Proyecciones actuales en Supabase: {len(current_projs)}")

# COMMAND ----------

# 3. Entrenar Prophet por plato y pronosticar 30 días
results = []

for dish_id in sorted(df['dish_id'].unique()):
    plato_df = df[df['dish_id'] == dish_id][['dia', 'unidades']].copy()
    plato_df.columns = ['ds', 'y']
    
    if len(plato_df) < 3:
        # Pocos datos, usar promedio
        projected = int(round(plato_df['y'].mean() * 30))
    else:
        try:
            model = Prophet(yearly_seasonality=False, weekly_seasonality=True,
                          daily_seasonality=False, interval_width=0.95)
            model.fit(plato_df)
            future = model.make_future_dataframe(periods=30)
            forecast = model.predict(future)
            projected = int(round(forecast['yhat'].tail(30).sum()))
        except:
            projected = int(round(plato_df['y'].mean() * 30))
    
    projected = max(projected, 1)  # mínimo 1
    results.append({'dish_id': dish_id, 'projected_units': projected})

# COMMAND ----------

# 4. Platos sin ventas históricas: mantener proyección actual o default 30
for did, proj in current_projs.items():
    if did not in [r['dish_id'] for r in results]:
        results.append({
            'dish_id': did,
            'projected_units': max(proj.get('projected_units', 30), 1)
        })

print(f"Total platos a actualizar: {len(results)}")

# COMMAND ----------

# 5. Escribir en Supabase via bulk API
updated = 0
for r_item in results:
    did = r_item['dish_id']
    proj = current_projs.get(did, {})
    pid = proj.get('id')
    if not pid:
        continue
    payload = {'projected_units': r_item['projected_units'],
               'updated_at': datetime.utcnow().isoformat()}
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/sales_projections",
        headers=HEADERS,
        params={"id": f"eq.{pid}"},
        json=payload
    )
    if resp.status_code in (200, 204):
        updated += 1

print(f"Actualizadas {updated} proyecciones en Supabase")
print("✅ Ve a /projections para ver los resultados")
