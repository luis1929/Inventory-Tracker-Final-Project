-- Fudness.co integration tables
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS fudness_products (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price DECIMAL(12,2),
    regular_price DECIMAL(12,2),
    in_stock BOOLEAN DEFAULT false,
    categories TEXT[] DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    description TEXT DEFAULT '',
    variations JSONB DEFAULT '[]',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fudness_orders (
    id BIGINT PRIMARY KEY,
    status TEXT DEFAULT '',
    currency TEXT DEFAULT 'COP',
    date_created TIMESTAMPTZ,
    total DECIMAL(12,2) DEFAULT 0,
    customer_name TEXT DEFAULT '',
    customer_email TEXT DEFAULT '',
    customer_phone TEXT DEFAULT '',
    items JSONB DEFAULT '[]',
    shipping_address JSONB DEFAULT '{}',
    payment_method TEXT DEFAULT '',
    payment_status TEXT DEFAULT '',
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fudness_sync_log (
    id BIGSERIAL PRIMARY KEY,
    sync_type TEXT NOT NULL,
    status TEXT NOT NULL,
    items_count INT DEFAULT 0,
    message TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
