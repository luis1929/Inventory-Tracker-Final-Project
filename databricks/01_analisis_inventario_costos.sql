# Databricks notebook source
# MAGIC %md
# MAGIC # Análisis de Inventario y Costos
# MAGIC Ejecutar después del sync para reportes semanales.

# COMMAND ----------

-- MAGIC %sql
-- Inventario por clasificación
SELECT classification,
       COUNT(*) AS ingredientes,
       ROUND(SUM(count * cost), 0) AS valor_inventario_actual
FROM ingredient_table
GROUP BY classification
ORDER BY valor_inventario_actual DESC;

-- COMMAND ----------

-- MAGIC %sql
-- Ingredientes por debajo del stock mínimo
SELECT name, measure, count AS stock_actual, min_stock,
       ROUND(count - min_stock, 2) AS diferencia,
       CASE WHEN count <= 0 THEN 'SIN STOCK'
            WHEN count < min_stock THEN 'BAJO'
            ELSE 'OK' END AS estado
FROM ingredient_table
WHERE count <= min_stock
ORDER BY diferencia ASC;

-- COMMAND ----------

-- MAGIC %sql
-- Platos con mayor costo de ingredientes
SELECT d.dish_name, d.category,
       d.cost_total AS costo_plato,
       d.sale_price,
       ROUND((d.sale_price - d.cost_total) / d.sale_price * 100, 1) AS margen_porcentaje
FROM menu_board d
WHERE d.cost_total > 0
ORDER BY d.cost_total DESC
LIMIT 20;

-- COMMAND ----------

-- MAGIC %sql
-- Ventas totales por día
SELECT DATE(created_at) AS dia,
       ROUND(SUM(total_sale), 0) AS ventas,
       ROUND(SUM(total_cost), 0) AS costos,
       ROUND(SUM(total_profit), 0) AS ganancia
FROM daily_sales
GROUP BY DATE(created_at)
ORDER BY dia DESC;
