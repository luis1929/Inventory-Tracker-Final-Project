-- Step 1: Add menu_board columns to fudness_products
ALTER TABLE fudness_products
  ADD COLUMN IF NOT EXISTS menu_board_dish_id BIGINT REFERENCES menu_board(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS dish_name TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'General',
  ADD COLUMN IF NOT EXISTS sort_order INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'activo',
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS cost_total DECIMAL(12,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS portion_weight_g DECIMAL(10,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS protein_g DECIMAL(10,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS calories DECIMAL(10,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS carbs_g DECIMAL(10,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fat_g DECIMAL(10,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fiber_g DECIMAL(10,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS sodium_mg DECIMAL(10,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS overhead_cost DECIMAL(12,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS sale_price DECIMAL(12,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT '';

-- Step 2: Remove old columns no longer needed (keep as aliases)
-- Keep slug as PK, name as alias for dish_name from now on

-- Step 3: Populate fudness_products from menu_board data
UPDATE fudness_products fp
SET
  dish_name = mb.dish_name,
  category = mb.category,
  sort_order = mb.sort_order,
  status = mb.status,
  created_at = mb.created_at,
  cost_total = mb.cost_total,
  portion_weight_g = mb.portion_weight_g,
  protein_g = mb.protein_g,
  calories = mb.calories,
  carbs_g = mb.carbs_g,
  fat_g = mb.fat_g,
  fiber_g = mb.fiber_g,
  sodium_mg = mb.sodium_mg,
  overhead_cost = mb.overhead_cost,
  sale_price = mb.sale_price,
  menu_board_dish_id = mb.id
FROM menu_board mb
WHERE UPPER(TRIM(fp.name)) = UPPER(TRIM(mb.dish_name));

-- Step 4: For products WITHOUT a menu_board dish, populate name into dish_name
UPDATE fudness_products
SET dish_name = name
WHERE dish_name = '';

-- Step 5: Drop redundant columns that now live in menu_board side
-- We keep fudness_products as the canonical source + enriched menu data
