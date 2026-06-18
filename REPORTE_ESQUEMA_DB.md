# Reporte de Esquema de Base de Datos — KitchenMaster Inventory Tracker

## Plataforma
- **Motor:** PostgreSQL 15+ (vía Supabase)
- **API REST:** PostgREST — todas las operaciones son HTTP directos, sin ORM
- **Proyecto:** `uapulmxutzezodmxavdd`
- **Endpoint REST:** `https://uapulmxutzezodmxavdd.supabase.co/rest/v1/`
- **Autenticación DB:** Service Role Key con rol `service_role` (scripts de carga) / `anon key` con RLS (producción)

---

## 1. `ingredient_table` — Ingredientes / Materia Prima

Tabla principal que almacena cada insumo del inventario.

| Columna | Tipo | Restricciones | Default | Descripción |
|---|---|---|---|---|
| `name` | TEXT | **PK** | — | Nombre único del ingrediente |
| `count` | DECIMAL | | 0 | Cantidad en inventario |
| `cost` | DECIMAL | | 0 | Precio de compra en COP |
| `measure` | TEXT | | '' | Unidad de medida base (`kg`, `g`, `ml`, `lb`, `u`) |
| `classification` | TEXT | | '' | Categoría (12 clasificaciones) |
| `brand` | TEXT | | '' | Marca comercial |
| `supplier` | TEXT | | '' | Proveedor o distribuidor |
| `presentation` | TEXT | | '' | Formato de venta al público |
| `notes` | TEXT | | '' | Observaciones adicionales |
| `user_id` | UUID | | `auth.uid()` | Propietario del registro (RLS) |

**PK:** `name`
**RLS:** Filtro por `user_id`

---

## 2. `recipe_table` — Recetas (Legacy)

Tabla original de recetas. Las recetas actuales se manejan en `menu_board` + `menu_recipe_items`.

| Columna | Tipo | Restricciones | Default | Descripción |
|---|---|---|---|---|
| `recipe_id` | BIGINT | PK (auto) | — | ID auto-incremental |
| `recipe_name` | TEXT | UNIQUE, NOT NULL | — | Nombre de la receta |
| `user_id` | UUID | | `auth.uid()` | Propietario |

**Estado:** Legacy — ya no se usa activamente. Las recetas actuales están en `menu_board`.

---

## 3. `recipe_ingredients_table` — Ingredientes de Recetas (Legacy)

| Columna | Tipo | Restricciones | Default | Descripción |
|---|---|---|---|---|
| `id` | BIGINT | PK (auto) | — | |
| `recipe_id` | BIGINT | FK → `recipe_table.recipe_id`, NOT NULL | — | |
| `ingredient_name` | TEXT | NOT NULL | — | |
| `quantity_needed` | DECIMAL | | 0 | |
| `measure` | TEXT | | '' | |
| `user_id` | UUID | | `auth.uid()` | |

**Estado:** Legacy — reemplazada por `menu_recipe_items`.

---

## 4. `user_profiles` — Usuarios y Roles

Almacena el perfil de cada usuario y su rol para el panel de administración.

| Columna | Tipo | Restricciones | Default | Descripción |
|---|---|---|---|---|
| `id` | UUID | **PK** | — | UUID del usuario (sync con Supabase Auth) |
| `email` | TEXT | **UNIQUE**, NOT NULL | — | Correo electrónico |
| `role` | TEXT | NOT NULL | `'user'` | `'user'` o `'admin'` |
| `created_at` | TIMESTAMPTZ | | `NOW()` | Fecha de registro |

**PK:** `id`
**UK:** `email`
**Relación:** 1:1 con `auth.users` de Supabase (sync vía API)

---

## 5. `menu_board` — Platos del Menú / Planificador

Tabla principal del módulo de menú. Cada fila es un plato con su costeo y nutrición.

| Columna | Tipo | Restricciones | Default | Descripción |
|---|---|---|---|---|
| `id` | BIGINT | **PK** (GENERATED ALWAYS AS IDENTITY) | — | ID auto-incremental |
| `category` | TEXT | NOT NULL | — | Columna kanban (12 categorías) |
| `dish_name` | TEXT | NOT NULL | — | Nombre del plato |
| `sort_order` | INT | | 0 | Posición dentro de la columna |
| `status` | TEXT | | `'activo'` | Estado del plato |
| `cost_total` | DECIMAL(10,2) | | 0 | Costo final por porción (MP + overhead) |
| `overhead_cost` | DECIMAL(10,2) | | 0 | No-cuantificable / servicios / mano-de-obra |
| `portion_weight_g` | INT | | 150 | Gramaje total por porción |
| `protein_g` | DECIMAL(8,2) | | 0 | Proteína por porción (g) |
| `calories` | DECIMAL(8,2) | | 0 | Calorías por porción |
| `carbs_g` | DECIMAL(8,2) | | 0 | Carbohidratos por porción (g) |
| `fat_g` | DECIMAL(8,2) | | 0 | Grasa por porción (g) |
| `fiber_g` | DECIMAL(8,2) | | 0 | Fibra por porción (g) |
| `sodium_mg` | DECIMAL(8,2) | | 0 | Sodio por porción (mg) |
| `created_at` | TIMESTAMPTZ | | `NOW()` | Fecha de creación |

**PK:** `id`

---

## 6. `menu_recipe_items` — Ingredientes de Cada Plato

Almacena los ingredientes individuales que componen cada plato, con su gramaje y costo específico.

| Columna | Tipo | Restricciones | Default | Descripción |
|---|---|---|---|---|
| `id` | BIGINT | **PK** (GENERATED ALWAYS AS IDENTITY) | — | ID auto-incremental |
| `dish_id` | BIGINT | **FK** → `menu_board(id)` ON DELETE CASCADE, NOT NULL | — | Plato al que pertenece |
| `ingredient_name` | TEXT | NOT NULL | — | Nombre del ingrediente |
| `quantity_grams` | DECIMAL(10,2) | NOT NULL | 0 | Gramos del ingrediente por porción |
| `unit_cost` | DECIMAL(10,4) | | 0 | $/gramo específico para esta receta |

**PK:** `id`
**FK:** `dish_id` → `menu_board(id)` con borrado en cascada

---

## 7. `auth.users` — Tabla Interna de Supabase Auth

Gestionada automáticamente por Supabase Auth (`gotrue`). No se modifica directamente.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID | PK |
| `email` | TEXT | Correo (único) |
| `encrypted_password` | TEXT | Hash de contraseña |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| ... | | (otras columnas internas de Supabase) |

**Relación:** `user_profiles.id` = `auth.users.id`

---

## Diagrama de Relaciones

```
┌───────────────────────┐
│     auth.users        │  (Supabase Auth — gestionada automáticamente)
├───────────────────────┤
│ id (UUID) ◄────┐      │
│ email          │      │
└────────────────┘      │
                        │ 1:1
┌───────────────────────┐
│    user_profiles      │
├───────────────────────┤
│ id (UUID) ────────────┘
│ email (UNIQUE)
│ role ('user'|'admin')
│ created_at
└───────────────────────┘

┌───────────────────────────┐
│    ingredient_table       │  ← ~343 registros
├───────────────────────────┤
│ name (PK)                 │
│ classification            │
│ brand                     │
│ supplier                  │
│ presentation              │
│ cost / count / measure    │
│ notes                     │
│ user_id                   │
└───────────────────────────┘
       │ (referenciado por nombre)
       ▼
┌───────────────────────────────┐
│     menu_board                │  ← ~101 platos
├───────────────────────────────┤
│ id (PK)                       │
│ category                      │
│ dish_name                     │
│ cost_total / overhead_cost    │
│ portion_weight_g              │
│ protein_g / calories / ...    │
│ created_at                    │
└───────────┬───────────────────┘
            │ 1:N (FK: dish_id)
            ▼
┌───────────────────────────────┐
│   menu_recipe_items           │  ← ingredientes por plato
├───────────────────────────────┤
│ id (PK)                       │
│ dish_id (FK → menu_board.id)  │
│   ON DELETE CASCADE           │
│ ingredient_name               │
│ quantity_grams                │
│ unit_cost                     │
└───────────────────────────────┘
       │ (referenciado por nombre)
       ▼
┌───────────────────────────┐
│    ingredient_table       │  (misma tabla de arriba)
│    (costo fallback)       │
└───────────────────────────┘

┌───────────────────────────────┐
│     recipe_table  (legacy)    │  ← ya no se usa
├───────────────────────────────┤
│ recipe_id                     │
│ recipe_name                   │
└───────────┬───────────────────┘
            │ 1:N
            ▼
┌───────────────────────────────┐
│ recipe_ingredients_table (leg)│
├───────────────────────────────┤
│ recipe_id (FK)                │
│ ingredient_name               │
│ quantity_needed               │
└───────────────────────────────┘
```

---

## Resumen de Tablas

| # | Tabla | Propósito | Registros | Estado |
|---|---|---|---|---|
| 1 | `ingredient_table` | Materia prima / insumos | ~343 | Activo |
| 2 | `recipe_table` | Recetas (legacy) | ~0 | Legacy |
| 3 | `recipe_ingredients_table` | Ingredientes de recetas (legacy) | ~0 | Legacy |
| 4 | `user_profiles` | Usuarios y roles | ~1-3 | Activo |
| 5 | `menu_board` | Platos del menú con costeo y nutrición | ~101 | Activo |
| 6 | `menu_recipe_items` | Ingredientes por plato con gramajes | ~— | Activo |
| 7 | `auth.users` | Autenticación (interna Supabase) | ~1-3 | Gestionado por Supabase |

## Convenciones de Nombres

- **Snake case** en todas las tablas y columnas
- **PK:** `id` o `name` (según la tabla) — `GENERATED ALWAYS AS IDENTITY` para auto-incrementales
- **FK:** `{tabla_origen}_id` → `{tabla_destino}(id)`
- **Soft delete:** No implementado (borrado físico directo)

## Migraciones

Las migraciones se ejecutan vía:
1. **Supabase SQL Editor** (migraciones manuales) — cuando el Management API no está disponible
2. **Endpoint `/api/admin/migrate`** (POST) — ejecuta SQL vía Management API desde la app

*Documento generado el 17 de junio de 2026*
