# Databricks notebook source
# MAGIC %md
# MAGIC # 📊 Dashboard Completo - KitchenMaster
# MAGIC
# MAGIC Copia cada query en el **SQL Editor** de Databricks y crea visualizaciones.
# MAGIC
# MAGIC ---

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. KPI: Valor Total del Inventario

# COMMAND ----------

-- MAGIC %sql
-- KPI 1: Valor total
SELECT 'Valor Total Inventario' AS kpi,
       ROUND(SUM(count * cost), 0) AS valor_cop
FROM ingredient_table
WHERE cost > 0;

-- KPI 2: Total ingredientes
SELECT 'Total Ingredientes' AS kpi, COUNT(*) AS valor FROM ingredient_table

-- KPI 3: Platos en menú
SELECT 'Platos en Menú' AS kpi, COUNT(*) AS valor FROM menu_board

-- KPI 4: Ventas totales (histórico)
SELECT 'Ventas Totales' AS kpi, ROUND(SUM(total_sale), 0) AS valor
FROM daily_sales

-- KPI 5: Ganancia total
SELECT 'Ganancia Neta' AS kpi, ROUND(SUM(total_profit), 0) AS valor
FROM daily_sales

-- KPI 6: Ventas hoy
SELECT 'Ventas Hoy' AS kpi,
       ROUND(SUM(total_sale), 0) AS valor
FROM daily_sales
WHERE DATE(created_at) = CURRENT_DATE

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Ingredientes con Mayor Costo (Top 20)

# COMMAND ----------

-- MAGIC %sql
-- Bar chart: Top 20 ingredientes más costosos
SELECT name,
       ROUND(cost, 0) AS costo_unitario,
       measure,
       ROUND(count * cost, 0) AS valor_total_inventario
FROM ingredient_table
WHERE cost > 0
ORDER BY cost DESC
LIMIT 20

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Distribución por Clasificación (Pie chart)

# COMMAND ----------

-- MAGIC %sql
-- Pie: Valor de inventario por clasificación
SELECT classification,
       COUNT(*) AS cantidad,
       ROUND(SUM(count * cost), 0) AS valor_total
FROM ingredient_table
WHERE cost > 0
GROUP BY classification
ORDER BY valor_total DESC

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Stock Bajo (alerta roja)

# COMMAND ----------

-- MAGIC %sql
-- Tabla: Ingredientes por debajo del mínimo
SELECT name,
       measure,
       ROUND(count, 1) AS stock_actual,
       ROUND(min_stock, 1) AS stock_minimo,
       ROUND(count - min_stock, 1) AS diferencia,
       CASE WHEN count <= 0 THEN '🔴 SIN STOCK'
            WHEN count < min_stock THEN '🟡 BAJO'
            ELSE '🟢 OK' END AS estado
FROM ingredient_table
WHERE count <= min_stock
ORDER BY diferencia ASC
LIMIT 30

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Platos con Mejor/Menor Margen

# COMMAND ----------

-- MAGIC %sql
-- Bar chart: Rentabilidad por plato
SELECT dish,
       ROUND(cost_total, 0) AS costo_plato,
       ROUND(sale_price, 0) AS precio_venta,
       ROUND(sale_price - cost_total, 0) AS ganancia_neta,
       ROUND((sale_price - cost_total) / NULLIF(sale_price, 0) * 100, 1) AS margen_pct
FROM menu_board
WHERE cost_total > 0 AND sale_price > 0
ORDER BY margen_pct DESC
LIMIT 20

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Ventas por Día (Time series)

# COMMAND ----------

-- MAGIC %sql
-- Line chart: Ventas diarias
SELECT DATE(created_at) AS fecha,
       ROUND(SUM(total_sale), 0) AS ventas,
       ROUND(SUM(total_cost), 0) AS costos,
       ROUND(SUM(total_profit), 0) AS ganancia
FROM daily_sales
GROUP BY DATE(created_at)
ORDER BY fecha DESC
LIMIT 30

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Proyecciones vs Ventas Reales (si hay datos)

# COMMAND ----------

-- MAGIC %sql
-- Bar chart: Proyecciones por plato
SELECT dish_name,
       ROUND(projected_units, 0) AS unidades_poyectadas,
       ROUND(unit_cost, 0) AS costo_unitario,
       ROUND(projected_units * unit_cost, 0) AS costo_total_proyectado
FROM sales_projections
WHERE is_active = TRUE
ORDER BY projected_units DESC
LIMIT 20

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Proveedores (Top 10)

# COMMAND ----------

-- MAGIC %sql
-- Tabla: Gastos por proveedor
SELECT supplier,
       COUNT(*) AS productos,
       ROUND(SUM(count * cost), 0) AS valor_inventario
FROM ingredient_table
WHERE supplier IS NOT NULL AND supplier != '' AND cost > 0
GROUP BY supplier
ORDER BY valor_inventario DESC
LIMIT 10

# COMMAND ----------
# MAGIC %md
# MAGIC ## 9. Precios Competencia (Si hay datos)

# COMMAND ----------

-- MAGIC %sql
-- Comparativa: Nuestro costo vs supermercados
SELECT i.name AS ingrediente,
       i.supplier AS proveedor,
       ROUND(i.cost, 0) AS nuestro_costo,
       ROUND(AVG(CASE WHEN p.supermercado = 'Olímpica' THEN p.precio END), 0) AS olimpica,
       ROUND(AVG(CASE WHEN p.supermercado = 'Carulla' THEN p.precio END), 0) AS carulla,
       ROUND(AVG(CASE WHEN p.supermercado = 'Éxito' THEN p.precio END), 0) AS exito,
       ROUND(AVG(CASE WHEN p.supermercado = 'Makro' THEN p.precio END), 0) AS makro
FROM ingredient_table i
LEFT JOIN precios_competencia p ON i.name = p.ingrediente
WHERE i.cost > 0
GROUP BY i.name, i.supplier, i.cost
ORDER BY i.name ASC
LIMIT 30
