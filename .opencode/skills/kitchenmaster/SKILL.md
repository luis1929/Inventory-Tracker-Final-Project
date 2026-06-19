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
- **No base template** — each template is standalone with full nav bar copied.
- **No comments in code** — keep code clean, no explanatory comments.

## Route Naming
- Page routes: `def <name>_page()` (e.g., `dashboard_page`, `ingredients_page`).
- API routes: `def <action>_<resource>()` (e.g., `list_ingredients`, `create_sale`, `delete_ingredient`).
- API routes prefixed with `/api/`, page routes are bare paths.
- Route functions use `@app.route()` decorator directly (no blueprints).

## Error Handling
- API returns: `jsonify({"error": msg}), 400` or `jsonify({"message": msg}), 200`.
- JS uses `showMessage(msg, type)` with `success`/`error` classes.
- Page routes that fail redirect with `?error=` query param.
- Always wrap Supabase calls in try/except, return 500 on failure.

## Supabase REST API Patterns

### Table Constants (defined at top of `index.py`)
```python
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
```

### API Helper
```python
def api_req(method, table, data=None, params=None, extra_headers=None):
    config = get_api_config()
    url = f"{config['url']}/rest/v1/{table}"
    headers = {**config['headers'], **(extra_headers or {})}
    r = requests.request(method, url, json=data, params=params, headers=headers)
    if r.status_code >= 400:
        raise Exception(f"Supabase error {r.status_code}: {r.text}")
    try: return r.json()
    except: return []
```

### Common Query Patterns
```python
# List all, ordered
api_req("GET", T_MENU, params={"select": "*", "order": "category.asc"})

# Single record by ID
api_req("GET", T_MENU, params={"id": f"eq.{dish_id}", "select": "*"})

# Filter by field
api_req("GET", T_INGS, params={"classification": f"eq.{cat}"})

# Multiple IDs
api_req("GET", T_MENU, params={"id": f"in.({','.join(map(str,ids))})"})

# Upsert (insert or update by primary key)
api_req("POST", T_INGS, data=payload,
    extra_headers={"Prefer": "resolution=merge-duplicates"})

# Delete with return
api_req("DELETE", T_MENU, params={"id": f"eq.{id}"},
    extra_headers={"Prefer": "return=representation"})

# Select specific columns
api_req("GET", T_INGS, params={"select": "name,cost,count"})
```

## Auth
- Supabase Auth (email/password) + demo fallback.
- Decorators: `@login_required` (page routes), `@api_auth_required` (API routes).
- Admin check via `ADMIN_EMAILS` env var or `user_profiles.role`.
- User session in `flask.session`.
- Demo session auto-created if no user logged in (`_ensure_demo_session()`).

## Cost & Units
- **All costs in COP** (Colombian Pesos).
- `menu_recipe_items.unit_cost` stores **$/gram** (calculated as `ingredient_table.cost * _cost_multiplier(measure)`).
- `_cost_multiplier(measure)` converts: g→0.001, kg→1, lb→0.453592, l→1, ml→0.001, oz→0.0283495.
- Dish cost formula: `SUM(qty * unit_cost)` — **no `/1000` divisor** since `unit_cost` is already per-gram.

```python
# In _compute_dish_cost(dish_id):
cost = qty * unit_cost  # unit_cost is already $/gram
# sale_price - cost_total = profit per dish
```

## Templates & Nav
- All templates in `templates/` using Jinja2 + inline `<script>` at bottom.
- Nav uses `.nav-dropdown` CSS class for dropdowns.
- Every template includes the full nav bar (copied pattern, not inherited).
- Active page marked with `class="active"` on the `<a>` tag.
- Spanish UI throughout.
- Nav items: Inicio, Compras (dropdown: Comp x Stock, Comp x Proy Venta), Ver Tablas (dropdown), Dashboard, Precios, Admin (if admin).
- `context_processor` injects `is_admin` into all templates.

## Inline JS Conventions
```javascript
// Each template has a <script> block at the bottom
// Uses fetch() with async/await
async function loadData() {
    const res = await fetch('/api/endpoint');
    const data = await res.json();
    renderData(data);
}

// Show user messages
showMessage('Texto', 'success' | 'error');

// Chart.js initialization (dashboard.html, analytics.html)
new Chart(document.getElementById('chartId'), {
    type: 'bar' | 'pie' | 'line' | 'doughnut',
    data: { labels: [...], datasets: [{ data: [...], ... }] },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
});
```

## Dashboard API Shape
`GET /api/dashboard` returns:
```json
{
  "kpis": { "ganancia_total": float, "total_ingredientes": int, "total_platos": int, "valor_inventario": float, "ventas_totales": float },
  "clasificacion": [{ "classification": str, "count": int, "total_value": float }],
  "top_costosos": [{ "dish_name": str, "cost_total": float }],
  "margenes": [{ "dish_name": str, "sale_price": float, "cost_total": float, "margen": float }],
  "ventas_diarias": [{ "date": str, "total_sale": float }],
  "proyecciones": [{ "dish_name": str, "projected_units": int }],
  "proveedores": [{ "supplier": str, "count": int, "total_value": float }],
  "stock_bajo": [{ "name": str, "count": float, "min_stock": float, "supplier": str }]
}
```

## CSS Conventions
- Custom properties in `:root {}` at top of `styles.css`.
- Colors: `--cream` (#f8f4ef), `--cream-dark` (#e8ddd0), `--primary` (#d4a353 gold), `--danger` (#c0392b), `--text` (#1a1a2e).
- Fonts: Playfair Display (headings), Inter (body) — Google Fonts.
- Class naming: `.content-card`, `.form-row`, `.table-wrapper`, `.hero-content`, `.dashboard-grid`.
- Dashboard grid: `display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px;`
- Nav: fixed top, flexbox layout, dark background (#1a1a2e).

## Shopping List Modes
- `GET /shopping-list?mode=stock` — Restock based on current inventory vs min_stock.
- `GET /shopping-list?mode=sales` — Restock based on sales projections.
- Both modes generate a list grouped by supplier with calculated quantities.

## POS Flow
```python
# POST /api/pos/sell
# 1. Create daily_sales record with total_sale, total_cost, total_profit
# 2. Create sale_items records (one per dish)
# 3. Deduct inventory: ingredient_table.count -= quantity_needed
# All in sequence (no transaction — Supabase REST doesn't support transactions)
```

## Price Data
- `precios_competencia` table: `ingrediente`, `supermercado`, `producto`, `precio`, `presentacion`, `url`, `fecha_scrape`.
- Supermarkets: Olímpica, Carulla, Éxito, Makro.
- Endpoints: `GET /api/precios`, `PUT /api/precios` (upsert), `POST /api/precios/seed`.
- Prices editable inline on `/precios` page (click cell → edit → save).

## Databricks
- Workspace: `https://dbc-7c6d1fe1-d2d5.cloud.databricks.com`.
- Job ID: 668643130057860 (`sync-supabase-diario`), runs at 3:00 AM daily (America/Bogota).
- Secret scope: `supabase/service_key` for Supabase credentials.
- Notebooks in `databricks/` directory mirror those uploaded to workspace `/Users/lbarrera1929@gmail.com/sync/`.
- 3 tasks in job: sync (ingredients → Databricks) → forecast (Prophet) → scraper (competitor prices).
- Delta tables mirror Supabase tables for analytics.

## Migrations
- SQL files in `migrations/` folder.
- Executed via `POST /api/admin/migrate` (admin only).
- Naming: `NNN_description.sql` (e.g., `001_create_sales_projections.sql`).

## Vercel Deployment
- `vercel.json` routes `/*` → `api/index.py`.
- Push to `main` → auto-deploys.
- Serverless Python functions (15 MB max).
- No CI/CD config — Vercel webhook handles deployment.

## Git
- Single `main` branch.
- Remote: `https://github.com/luis1929/Inventory-Tracker-Final-Project.git`.
- Deploy: push to `main` → Vercel auto-deploys.
- `.env` is gitignored (contains live Supabase keys).
- Commits in Spanish or English, concise, prefixed with action.

## Naming
- Python route functions: snake_case (e.g., `dashboard_page`, `list_ingredients`).
- JS functions: camelCase (e.g., `loadInventory`, `renderCart`, `toggleCartItem`).
- CSS classes: kebab-case, BEM-like nesting.
- DB columns: snake_case.
- HTML ids: camelCase (e.g., `searchInput`, `formSubmitBtn`).
- Table constants: `T_` prefix (e.g., `T_INGS`, `T_MENU`).
- Env vars: `UPPER_SNAKE_CASE`.

## HTML Patterns
- `<section class="hero">` for page headers with badge + h1 + description.
- `<div class="container">` for main content.
- `<div class="content-card">` for each card/section.
- `<div class="form-row">` for horizontal form layouts.
- `<div class="table-wrapper"><table>...</table></div>` for tables.
- Message display: `<div id="formMessage" class="message"></div>`.
- Back link: `<a href="/" class="back-link">&larr; Volver al inicio</a>`.
