-- Tabla de Proyección de Ventas para KitchenMaster
-- Ejecutar en el SQL Editor del Dashboard de Supabase

CREATE TABLE IF NOT EXISTS sales_projections (
    id BIGSERIAL PRIMARY KEY,
    dish_id BIGINT REFERENCES menu_board(id) ON DELETE CASCADE,
    dish_name TEXT NOT NULL,
    projected_units INTEGER NOT NULL DEFAULT 30,
    unit_cost DECIMAL(12,2) NOT NULL DEFAULT 0,
    total_dish_cost DECIMAL(12,2) NOT NULL DEFAULT 0,
    start_date DATE NOT NULL DEFAULT CURRENT_DATE,
    end_date DATE NOT NULL DEFAULT (CURRENT_DATE + INTERVAL '30 days'),
    estimated_qty DECIMAL(12,2) NOT NULL DEFAULT 0,
    estimated_cost DECIMAL(12,2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sales_projections_dish_id ON sales_projections(dish_id);
CREATE INDEX IF NOT EXISTS idx_sales_projections_active ON sales_projections(is_active);
