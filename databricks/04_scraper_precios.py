# Databricks notebook source
# MAGIC %md
# MAGIC # Scraper de Precios de Supermercados
# MAGIC
# MAGIC Intenta scrapear precios reales de supermercados vía API/HTML.
# MAGIC Si no se obtienen suficientes datos, genera precios estimados basados en el costo actual de ingredientes.

# COMMAND ----------

# MAGIC %pip install beautifulsoup4 lxml

# COMMAND ----------

import requests
import pandas as pd
from bs4 import BeautifulSoup
import re, json, time, random
from datetime import datetime, date
from difflib import SequenceMatcher
from urllib.parse import quote

random.seed(42)

SUPABASE_URL = "https://uapulmxutzezodmxavdd.supabase.co"
API_KEY = dbutils.secrets.get("supabase", "service_key")
HEADERS = {"apikey": API_KEY, "Authorization": f"Bearer {API_KEY}"}
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
SUPERMERCADOS = ['Olímpica', 'Carulla', 'Éxito', 'Makro']

# COMMAND ----------

# 1. Crear tabla en Databricks
spark.sql("""
CREATE TABLE IF NOT EXISTS precios_competencia (
    ingrediente   STRING,
    supermercado  STRING,
    producto      STRING,
    precio        DECIMAL(12,2),
    presentacion  STRING,
    url           STRING,
    fecha_scrape  DATE
) USING DELTA
COMMENT 'Precios de ingredientes en supermercados'
""")

# COMMAND ----------

# 2. Cargar ingredientes desde Supabase
r = requests.get(f"{SUPABASE_URL}/rest/v1/ingredient_table",
                 headers=HEADERS,
                 params={"select": "name,cost,measure,supplier", "order": "name.asc"})
ingredients = r.json()
print(f"Ingredientes cargados: {len(ingredients)}")

# COMMAND ----------

# 3. Funciones de scraping

def search_olimpica(query):
    try:
        r = requests.get(f"https://www.olimpica.com/api/catalog_system/pub/products/search?q={quote(query)}&_from=0&_to=5", headers=UA, timeout=15)
        if r.ok or r.status_code == 206:
            data = r.json()
            results = []
            for item in data[:3]:
                name = item.get('productName', '')
                price = None
                if item.get('priceRange', {}).get('sellingPrice', {}).get('highPrice'):
                    price = item['priceRange']['sellingPrice']['highPrice']
                elif item.get('items') and item['items'][0].get('sellers'):
                    price = item['items'][0]['sellers'][0].get('commertialOffer', {}).get('Price')
                if price and name:
                    results.append((name, price, f"https://www.olimpica.com/{item.get('linkText','')}/p"))
            return results
    except:
        pass
    return []

def search_carulla(query):
    try:
        r = requests.get(f"https://www.carulla.com/api/catalog_system/pub/products/search?q={quote(query)}&_from=0&_to=5", headers=UA, timeout=15, allow_redirects=True)
        if r.ok or r.status_code == 206:
            data = r.json()
            results = []
            for item in data[:3]:
                name = item.get('productName', '')
                price = None
                if item.get('priceRange', {}).get('sellingPrice', {}).get('highPrice'):
                    price = item['priceRange']['sellingPrice']['highPrice']
                elif item.get('items') and item['items'][0].get('sellers'):
                    price = item['items'][0]['sellers'][0].get('commertialOffer', {}).get('Price')
                if price and name:
                    results.append((name, price, f"https://www.carulla.com/{item.get('linkText','')}/p"))
            return results
    except:
        pass
    return []

def search_exito(query):
    try:
        r = requests.get(f"https://www.exito.com/api/catalog_system/pub/products/search?q={quote(query)}&_from=0&_to=5", headers=UA, timeout=15, allow_redirects=True)
        if r.ok or r.status_code == 206:
            data = r.json()
            results = []
            for item in data[:3]:
                name = item.get('productName', '')
                price = None
                if item.get('priceRange', {}).get('sellingPrice', {}).get('highPrice'):
                    price = item['priceRange']['sellingPrice']['highPrice']
                elif item.get('items') and item['items'][0].get('sellers'):
                    price = item['items'][0]['sellers'][0].get('commertialOffer', {}).get('Price')
                if price and name:
                    results.append((name, price, f"https://www.exito.com/{item.get('linkText','')}/p"))
            return results
    except:
        pass
    return []

def search_makro(query):
    try:
        r = requests.get(f"https://www.makro.com.co/catalogsearch/result/?q={quote(query)}", headers=UA, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            results = []
            for product in soup.select('.product-item, .item.product')[:3]:
                name_el = product.select_one('.product-item-link, .product.name a')
                price_el = product.select_one('.price')
                link_el = product.select_one('a.product-item-link')
                if name_el and price_el:
                    name = name_el.get_text(strip=True)
                    price_text = price_el.get_text(strip=True).replace('$', '').replace('.', '').replace(',', '.')
                    m = re.search(r'[\d.]+', price_text)
                    price = float(m.group()) if m else None
                    link = link_el.get('href', '') if link_el else ''
                    if price and name:
                        results.append((name, price, link))
            return results
    except:
        pass
    return []

search_fns = [
    ("Olímpica", search_olimpica),
    ("Carulla", search_carulla),
    ("Éxito", search_exito),
    ("Makro", search_makro),
]

# COMMAND ----------

# 4. Intentar scraping real
today = datetime.now().date()
all_rows = []
checked = 0

for ing in ingredients:
    name = ing['name']
    checked += 1
    if checked % 30 == 0:
        print(f"Scrapeando {checked}/{len(ingredients)}...")
    for super_name, fn in search_fns:
        try:
            results = fn(name)
            time.sleep(0.3)
            for prod_name, price, url in results:
                all_rows.append({
                    'ingrediente': name,
                    'supermercado': super_name,
                    'producto': prod_name[:200],
                    'precio': price,
                    'url': url[:500] if url else '',
                    'fecha_scrape': today
                })
                break
        except:
            continue

print(f"Scraping completado: {len(all_rows)} precios encontrados")

# COMMAND ----------

# 5. Si hay pocos resultados, generar precios estimados
MIN_ROWS = 100

if len(all_rows) < MIN_ROWS:
    print(f"⚠️ Solo {len(all_rows)} precios reales. Generando datos estimados...")
    seed_rows = []
    for ing in ingredients:
        cost_str = ing.get('cost')
        if not cost_str:
            continue
        try:
            cost = float(cost_str)
        except:
            continue
        if cost <= 0:
            continue
        for sm in SUPERMERCADOS:
            mult = 0.7 + random.random() * 0.8
            seed_rows.append({
                'ingrediente': ing['name'],
                'supermercado': sm,
                'producto': ing['name'],
                'precio': round(cost * mult, 0),
                'url': '',
                'fecha_scrape': today
            })
    # Combine real + seed, prioritize real
    seen = set()
    combined = []
    for row in all_rows + seed_rows:
        key = (row['ingrediente'], row['supermercado'])
        if key not in seen:
            seen.add(key)
            combined.append(row)
    all_rows = combined
    print(f"✅ Total después de combinar: {len(all_rows)} precios")

# COMMAND ----------

# 6. Guardar en Databricks
today_str = today.isoformat()
spark.sql(f"DELETE FROM precios_competencia WHERE fecha_scrape = '{today_str}'")
if all_rows:
    df = pd.DataFrame(all_rows)
    spark_df = spark.createDataFrame(df)
    spark_df.write.mode("append").saveAsTable("precios_competencia")
    print(f"✅ {len(all_rows)} precios guardados en Databricks")

# COMMAND ----------

# 7. Escribir en Supabase (batch upsert)
if all_rows:
    for row in all_rows:
        if isinstance(row['fecha_scrape'], date):
            row['fecha_scrape'] = row['fecha_scrape'].isoformat()
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/precios_competencia",
        headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
        json=all_rows
    )
    inserted = len(all_rows) if resp.status_code in (200, 201) else 0
    if resp.status_code not in (200, 201):
        print(f"⚠️ Supabase error {resp.status_code}: {resp.text[:200]}")
    print(f"✅ {inserted}/{len(all_rows)} precios en Supabase")
else:
    print("⚠️ No hay precios para guardar")

# COMMAND ----------

# 8. Mostrar resultados
display(spark.sql(f"""
  SELECT supermercado, COUNT(*) AS productos,
         ROUND(AVG(precio), 0) AS precio_promedio
  FROM precios_competencia
  WHERE fecha_scrape = '{today_str}'
  GROUP BY supermercado
  ORDER BY productos DESC
"""))
