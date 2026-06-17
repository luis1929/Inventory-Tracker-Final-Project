-- Ejecutar en Supabase SQL Editor
-- https://supabase.com/dashboard/project/uapulmxutzezodmxavdd/sql/new

CREATE TABLE IF NOT EXISTS nutrition_table (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ingredient_name TEXT NOT NULL UNIQUE,
    classification TEXT DEFAULT '',
    calories_usda DECIMAL(10,2) DEFAULT 0,
    protein_g DECIMAL(10,2) DEFAULT 0,
    fat_g DECIMAL(10,2) DEFAULT 0,
    carbs_g DECIMAL(10,2) DEFAULT 0,
    fiber_g DECIMAL(10,2) DEFAULT 0,
    sodium_mg DECIMAL(10,2) DEFAULT 0,
    calories_protein DECIMAL(10,2) DEFAULT 0,
    calories_fat DECIMAL(10,2) DEFAULT 0,
    calories_carbs DECIMAL(10,2) DEFAULT 0,
    total_calories DECIMAL(10,2) DEFAULT 0,
    total_calories_no_fiber DECIMAL(10,2) DEFAULT 0
);

-- Enable RLS (same as other tables)
ALTER TABLE nutrition_table ENABLE ROW LEVEL SECURITY;

-- Allow all operations for authenticated users
CREATE POLICY "nutrition_table_all" ON nutrition_table
    FOR ALL USING (true) WITH CHECK (true);
