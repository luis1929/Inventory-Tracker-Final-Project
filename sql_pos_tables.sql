-- Ejecutar en Supabase SQL Editor
-- https://supabase.com/dashboard/project/uapulmxutzezodmxavdd/sql/new

-- Add sale_price to menu_board
ALTER TABLE menu_board ADD COLUMN IF NOT EXISTS sale_price DECIMAL(10,2) DEFAULT 0;

-- Daily sales header
CREATE TABLE IF NOT EXISTS daily_sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    total_sale DECIMAL(12,2) DEFAULT 0,
    total_cost DECIMAL(12,2) DEFAULT 0,
    total_profit DECIMAL(12,2) DEFAULT 0,
    items_count INT DEFAULT 0
);

-- Sale line items
CREATE TABLE IF NOT EXISTS sale_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sale_id BIGINT NOT NULL REFERENCES daily_sales(id) ON DELETE CASCADE,
    dish_id BIGINT NOT NULL,
    dish_name TEXT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    sale_price_unit DECIMAL(10,2) DEFAULT 0,
    cost_per_unit DECIMAL(10,2) DEFAULT 0,
    line_sale DECIMAL(12,2) DEFAULT 0,
    line_cost DECIMAL(12,2) DEFAULT 0,
    line_profit DECIMAL(12,2) DEFAULT 0
);

ALTER TABLE daily_sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE sale_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "daily_sales_all" ON daily_sales FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "sale_items_all" ON sale_items FOR ALL USING (true) WITH CHECK (true);
