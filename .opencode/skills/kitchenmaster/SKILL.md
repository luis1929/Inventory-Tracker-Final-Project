---
name: kitchenmaster
description: Project conventions for KitchenMaster (Inventory Tracker) — Flask + Supabase REST + Vanilla JS + Vercel + Databricks. Use when working on any feature, bugfix, or refactor in this repo.
metadata:
  stack: "Flask 2.x, Supabase PostgreSQL (REST API, no ORM), Jinja2, Vanilla JS, Chart.js CDN, Vercel serverless Python"
  language: "Python 3.10+, Spanish UI"
  currency: "COP (Colombian Pesos)"
  db: "Supabase via REST API at https://uapulmxutzezodmxavdd.supabase.co"
---

# KitchenMaster — Project Conventions

## Architecture
- **Single Flask app** in `api/index.py` (no blueprints).
- **No ORM** — Supabase accessed via `requests` REST API using helper `api_req(method, table, data, params, extra_headers)`.
- **All JS inline** in Jinja2 templates (no JS framework, no separate `.js` files).
- **Single CSS** file at `static/styles.css` with CSS custom properties.
- **Charts** via Chart.js 4.x loaded from CDN.
- **Databricks** notebooks in `databricks/` for daily sync, Prophet forecasting, and competitor price scraping.

## Supabase REST API Patterns
```python
# Table constants defined at top of index.py:
T_INGS = "ingredient_table"
T_MENU = "menu_board"
T_MENU_RECIPE = "menu_recipe_items"
T_SALES = "daily_sales"
T_SALE_ITEMS = "sale_items"
T_PROJECTIONS = "sales_projections"
T_RECIPES = "recipe_table"
T_RECIPE_INGS = "recipe_ingredients_table"
T_USERS = "user_profiles"
T_NUTRITION = "nutrition_table"
T_PRECIOS = "precios_competencia"

# API helper:
api_req("GET", T_MENU, params={"select": "*", "order": "category.asc"})

# Upsert with merge:
api_req("POST", T_INGS, data=payload,
    extra_headers={"Prefer": "resolution=merge-duplicates"})

# Filter syntax: "name=eq.value", "id=in.(1,2,3)"
# Delete with return: api_req("DELETE", T_MENU, params={"id": f"eq.{id}"},
#     extra_headers={"Prefer": "return=representation"})
```

## Auth
- Supabase Auth (email/password) + demo fallback.
- Decorators: `@login_required` (page routes), `@api_auth_required` (API routes).
- Admin check via `ADMIN_EMAILS` env var or `user_profiles.role`.
- User session in `flask.session`.

## Cost & Units
- **All costs in COP** (Colombian Pesos).
- `menu_recipe_items.unit_cost` stores **$/gram** (calculated as `ingredient_table.cost * _cost_multiplier(measure)`).
- `_cost_multiplier(measure)` converts: g→0.001, kg→1, lb→0.453592, l→1, ml→0.001, oz→0.0283495.
- Dish cost formula: `SUM(qty * unit_cost)` — **no `/1000` divisor** since `unit_cost` is already per-gram.

## Dish Costing Formula
```python
# In _compute_dish_cost(dish_id):
cost = qty * unit_cost  # unit_cost is already $/gram
# No /1000 needed
```

## Templates & Nav
- All templates in `templates/` using Jinja2 + inline `<script>`.
- Nav uses `.nav-dropdown` CSS class for dropdowns.
- Every template includes the full nav bar (copied pattern).
- Active page marked with `class="active"` on the `<a>` tag.
- Spanish UI throughout.

## CSS Conventions
- Custom properties in `:root {}` at top of `styles.css`.
- Colors: `--cream`, `--cream-dark`, `--primary` (gold), `--danger` (red), `--text` (dark).
- Fonts: Playfair Display (headings), Inter (body) — Google Fonts.
- Class naming: `.content-card`, `.form-row`, `.table-wrapper`, `.hero-content`.

## Price Data
- `precios_competencia` table: `ingrediente`, `supermercado`, `producto`, `precio`, `presentacion`, `url`, `fecha_scrape`.
- Supermarkets: Olímpica, Carulla, Éxito, Makro.
- Endpoints: `GET /api/precios`, `PUT /api/precios` (upsert), `POST /api/precios/seed`.

## Databricks
- Workspace: `https://dbc-7c6d1fe1-d2d5.cloud.databricks.com`.
- Job ID: 668643130057860 (`sync-supabase-diario`), runs at 3:00 AM daily (America/Bogota).
- Secret scope: `supabase/service_key` for Supabase credentials.
- Notebooks in `databricks/` directory mirror those uploaded to workspace `/Users/lbarrera1929@gmail.com/sync/`.

## Git
- Single `main` branch.
- Remote: `https://github.com/luis1929/Inventory-Tracker-Final-Project.git`.
- Deploy: push to `main` → Vercel auto-deploys.
- `.env` is gitignored (contains live Supabase keys).

## Naming
- Route functions: snake_case (e.g., `dashboard_page`, `list_ingredients`).
- JS functions: camelCase (e.g., `loadInventory`, `deleteIngredient`).
- CSS classes: kebab-case in names, BEM-like nesting.
- Table columns: snake_case.
