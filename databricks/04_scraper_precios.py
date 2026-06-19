# Databricks notebook source
# MAGIC %md
# MAGIC # Scraper de Precios de Supermercados
# MAGIC
# MAGIC Busca automáticamente cada ingrediente en 5 supermercados y guarda los precios en una tabla `precios_competencia`.

# COMMAND ----------

import requests
import pandas as pd
from bs4 import BeautifulSoup
import re, json, time
from datetime import datetime
from difflib import SequenceMatcher

SUPABASE_URL = "https://uapulmxutzezodmxavdd.supabase.co"
API_KEY = dbutils.secrets.get("supabase", "service_key")
HEADERS = {"apikey": API_KEY, "Authorization": f"Bearer {API_KEY}"}
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

# COMMAND ----------

# 1. Crear tabla en Databricks si no existe
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
                 params={"select": "name,classification,supplier", "order": "name.asc"})
ingredients = r.json()
print(f"Ingredientes a buscar: {len(ingredients)}")

# COMMAND ----------

# 3. Funciones de scraping por supermercado

def search_olimpica(query):
    url = f"https://www.olimpica.com/api/catalog_system/pub/products/search?q={requests.utils.quote(query)}&_from=0&_to=5"
    try:
        r = requests.get(url, headers=UA, timeout=15)
        if r.status_code == 200:
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
        url = f"https://www.carulla.com/api/catalog_system/pub/products/search?q={requests.utils.quote(query)}&_from=0&_to=5"
        r = requests.get(url, headers=UA, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            data = r.json()
            results = []
            for item in data[:3]:
                name = item.get('productName', '')
                price = None
                if item.get('priceRange', {}).get('sellingPrice', {}).get('highPrice'):
                    price = item['priceRange']['sellingPrice']['highPrice']
                if price and name:
                    results.append((name, price, f"https://www.carulla.com/{item.get('linkText','')}/p"))
            return results
    except:
        pass
    return []

def search_makro(query):
    try:
        url = f"https://www.makro.com.co/catalogsearch/result/?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=UA, timeout=15)
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
                    price = float(re.search(r'[\d.]+', price_text).group()) if re.search(r'[\d.]+', price_text) else None
                    link = link_el.get('href', '') if link_el else ''
                    if price and name:
                        results.append((name, price, link))
            return results
    except:
        pass
    return []

def search_exito(query):
    try:
        url = f"https://www.exito.com/api/catalog_system/pub/products/search?q={requests.utils.quote(query)}&_from=0&_to=5"
        r = requests.get(url, headers=UA, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            data = r.json()
            results = []
            for item in data[:3]:
                name = item.get('productName', '')
                price = None
                if item.get('priceRange', {}).get('sellingPrice', {}).get('highPrice'):
                    price = item['priceRange']['sellingPrice']['highPrice']
                if price and name:
                    results.append((name, price, f"https://www.exito.com/{item.get('linkText','')}/p"))
            return results
    except:
        pass
    return []

def search_mercadolibre(query):
    try:
        url = f"https://api.mercadolibre.com/sites/MCO/search?q={requests.utils.quote(query)}&limit=3"
        r = requests.get(url, headers=UA, timeout=15)
        if r.status_code == 200:
            data = r.json()
            results = []
            for item in data.get('results', [])[:3]:
                name = item.get('title', '')
                price = item.get('price')
                link = item.get('permalink', '')
                if price and name:
                    results.append((name, price, link))
            return results
    except:
        pass
    return []

# COMMAND ----------

# 4. Ejecutar scraping
supermarkets = [
    ("Olímpica", search_olimpica),
    ("Carulla", search_carulla),
    ("Éxito", search_exito),
    ("Makro", search_makro),
    ("MercadoLibre", search_mercadolibre),
]

today = datetime.now().date()
all_rows = []
checked = 0

for ing in ingredients:
    name = ing['name']
    checked += 1
    if checked % 20 == 0:
        print(f"Procesados {checked}/{len(ingredients)}...")
    
    for super_name, search_fn in supermarkets:
        try:
            results = search_fn(name)
            time.sleep(0.5)  # rate limit
            for prod_name, price, url in results:
                all_rows.append({
                    'ingrediente': name,
                    'supermercado': super_name,
                    'producto': prod_name[:200],
                    'precio': price,
                    'url': url[:500] if url else '',
                    'fecha_scrape': today
                })
                break  # solo el mejor match por supermercado
        except:
            continue

# COMMAND ----------

# 5. Guardar en Databricks
if all_rows:
    df = pd.DataFrame(all_rows)
    spark_df = spark.createDataFrame(df)
    spark_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("precios_competencia")
    print(f"✅ {len(all_rows)} precios guardados en Databricks")
else:
    print("⚠️ No se encontraron precios")

# COMMAND ----------

# 6. Escribir también en Supabase
from datetime import date

inserted = 0
for row in all_rows:
    payload = {
        'ingrediente': row['ingrediente'],
        'supermercado': row['supermercado'],
        'producto': row['producto'],
        'precio': row['precio'],
        'url': row['url'],
        'fecha_scrape': row['fecha_scrape'].isoformat() if isinstance(row['fecha_scrape'], date) else row['fecha_scrape'],
    }
    resp = requests.post(f"{SUPABASE_URL}/rest/v1/precios_competencia",
                         headers=HEADERS, json=payload)
    if resp.status_code in (200, 201):
        inserted += 1

print(f"✅ {inserted} precios guardados en Supabase (tabla: precios_competencia)")

# COMMAND ----------

# 7. Mostrar resultados
display(spark.sql("""
  SELECT supermercado, COUNT(*) AS productos,
         ROUND(AVG(precio), 0) AS precio_promedio
  FROM precios_competencia
  WHERE fecha_scrape = CURRENT_DATE
  GROUP BY supermercado
  ORDER BY productos DESC
"""))
