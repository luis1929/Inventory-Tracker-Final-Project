# Reporte de Carga de Datos — KitchenMaster Inventory Tracker

## 1. Plataforma de Base de Datos

**Supabase** (PostgreSQL relacional) sobre el proyecto `uapulmxutzezodmxavdd`.
- URL API REST: `https://uapulmxutzezodmxavdd.supabase.co/rest/v1/`
- Autenticación: Service Role Key (JWT con rol `service_role`, permisos totales)
- Versión: PostgreSQL 15+ con API REST estándar (PostgREST)
- Sin ORM — todas las operaciones son HTTP requests directos al REST API de Supabase

---

## 2. Tablas Utilizadas

### `ingredient_table`
Almacena cada insumo o materia prima con todos sus atributos.

| Columna | Tipo | Descripción |
|---|---|---|
| `name` | TEXT (PK) | Nombre único del ingrediente |
| `classification` | TEXT | Categoría (12 clasificaciones) |
| `brand` | TEXT | Marca comercial |
| `supplier` | TEXT | Proveedor / distribuidor |
| `presentation` | TEXT | Formato de venta (ej: "KILO", "FRASCO X 500 ML") |
| `cost` | DECIMAL | Precio de compra en pesos colombianos |
| `count` | DECIMAL | Cantidad actual en inventario |
| `measure` | TEXT | Unidad de medida base (`kg`, `g`, `ml`, `lb`, `u`) |

### `menu_board`
Cada plato del menú con su costeo y nutrición.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | BIGINT (PK) | ID auto-incremental |
| `category` | TEXT | Categoría (12 columnas del kanban) |
| `dish_name` | TEXT | Nombre del plato |
| `cost_total` | DECIMAL | Costo final (MP + overhead) |
| `overhead_cost` | DECIMAL | No-cuantificable/servicios/mano-de-obra |
| `portion_weight_g` | INT | Gramaje por porción |
| `protein_g`, `calories`, `carbs_g`, `fat_g`, `fiber_g`, `sodium_mg` | DECIMAL | Nutrición por porción |

### `menu_recipe_items`
Ingredientes individuales de cada plato con su gramaje y costo unitario.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | BIGINT (PK) | ID auto-incremental |
| `dish_id` | BIGINT (FK → `menu_board.id`) | Plato al que pertenece |
| `ingredient_name` | TEXT | Ingrediente usado |
| `quantity_grams` | DECIMAL | Gramos del ingrediente por porción |
| `unit_cost` | DECIMAL | $/gramo específico de esta receta (opcional; si es 0 se usa el costo de `ingredient_table`) |

---

## 3. Carga de Ingredientes (Materia Prima)

### Fuente de datos
Datos tabulares suministrados por el usuario en formato **TSV** (tab-separated values) directamente en la terminal.

### Formato de cada fila
```
CLASIFICACIÓN	NOMBRE	MARCA	PROVEEDOR	PRESENTACIÓN	COSTO	CANTIDAD
```

**Ejemplo real:**
```
ADEREZOS/CONDIMENTOS/ESPECIAS	PIMIENTA PICANTE ENTERA	SAYSA	OLIMPICA	CHAPETA X 25 GRAMOS	 2.400 	 96
```

### Procesamiento (script Python `load_ingredients.py`)

#### 3a. Parseo de precio
- Formato colombiano: punto (`.`) como separador de miles
- El script elimina todos los puntos y reemplaza coma (`,`) por punto (`.`) para decimales
- **Ejemplo:** `"2.400"` → `2400`, `"101.300"` → `101300`, `"4.990"` → `4990`
- Los valores sin costo se asignan a `0`

#### 3b. Inferencia de unidad de medida
Derivada automáticamente del campo `presentation` mediante reglas:

| Texto en presentación | Medida asignada |
|---|---|
| KILO, KILOS | `kg` |
| GRAMOS, G (con número) | `g` |
| ML (con número) | `ml` |
| LIBRA, LB | `lb` |
| UNIDAD | `u` |
| LITRO, LTS | `l` |
| Otro / no detectable | `u` (unidad) |

**Ejemplos:**
- `"KILO"` → `kg`
- `"FRASCO X 500 ML"` → `ml`
- `"BOLSA X 200 GRAMOS"` → `g`
- `"CHAPETA X 25 GRAMOS"` → `g`
- `"UNIDAD"` → `u`
- `"GARRAFA X 5000"` → `u` (no se especifica unidad)

#### 3c. Estrategia de inserción
- **Endpoint:** `POST /rest/v1/ingredient_table`
- **Header:** `Prefer: resolution=merge-duplicates`
  - Si el ingrediente ya existe por nombre, se **actualizan** los campos en vez de duplicar
  - Esto permite recargas seguras sin generar registros repetidos
- **Autenticación:** Service Role Key vía header `Authorization: Bearer` + `apikey`

#### 3d. Volumen cargado
- **Lote 1:** 81 ingredientes (aderezos, azúcares, cereales, frutas, grasas, lácteos, etc.)
- **Lote 2:** 41 ingredientes (lácteos restantes, legumbres, proteínas cárnicas, semillas, vegetales)
- **Lote 3:** 36 ingredientes (vegetales restantes)
- **Total:** ~158 ingredientes nuevos + 185 importados previamente ≈ **343 ingredientes en total**

---

## 4. Carga de Recetas (Platos del Menú)

### Fuente de datos
Datos tabulares desde el usuario en formato texto con estructura **two-table**:

**Tabla izquierda — Costos:**
```
Categoría | Plato | Ingrediente | Gramaje
```

**Tabla derecha — Nutrición por porción:**
```
Plato | Proteína | Calorías | Carbohidratos | Grasa | Fibra | Sodio | Overhead
```

### Procesamiento

#### 4a. Inserción en `menu_board`
Cada plato único se inserta con:
- `category` → columna kanban (12 categorías: Arroz, Pollo/Pavo, Carne, Cerdo, Pescados/Mariscos, Quinoa, Pastas, Papa, Vegetales Frescos)
- `dish_name` → nombre del plato
- `sort_order` → posición dentro de la columna
- `overhead_cost` → costo de no-cuantificable/servicios/mano-de-obra
- Columnas de nutrición → `protein_g`, `calories`, `carbs_g`, `fat_g`, `fiber_g`, `sodium_mg`

#### 4b. Inserción en `menu_recipe_items`
Cada fila de ingrediente dentro de un plato se inserta con:
- `dish_id` → FK al plato recién creado
- `ingredient_name` → nombre exacto del ingrediente (debe coincidir con `ingredient_table.name`)
- `quantity_grams` → gramos usados por porción
- `unit_cost` → $/gramo específico (opcional)

#### 4c. Costeo automático
- Si `unit_cost > 0` → se usa ese valor directamente
- Si `unit_cost = 0` → se busca el costo en `ingredient_table` usando el nombre del ingrediente y su `measure` para convertir a $/gramo
- `raw_cost` = suma de (`quantity_grams` × `unit_cost`)
- `cost_total` = `raw_cost` + `overhead_cost`
- El costo final se persiste en `menu_board.cost_total`

#### 4d. Volumen cargado
- ~101 platos distribuidos en 12 categorías:
  - Arroz: ~22
  - Pollo/Pavo: 10
  - Carne: 12
  - Cerdo: 9
  - Pescados/Mariscos: 19
  - Quinoa: 2
  - Pastas: 4
  - Papa: 16
  - Vegetales Frescos: 6

---

## 5. Filtros y Transformaciones Aplicadas

### 5a. Clasificación de ingredientes
Los ingredientes se agrupan en 12 categorías normalizadas (dropdown en UI):

| Categoría en datos fuente | Categoría normalizada |
|---|---|
| ADEREZOS/CONDIMENTOS/ESPECIAS | Aderezos/Condimentos/Especias |
| AZUCARES - ENDULZANTES | Azúcares - Endulzantes |
| CEREALES - TUBERCULOS - CARBOHIDRATOS | Cereales - Tubérculos - Carbohidratos |
| FRUTAS | Frutas |
| FRUTAS - GRASAS | Frutas - Grasas |
| FRUTOS DESHIDRATADOS - AZUCARES | Frutos Deshidratados - Azúcares |
| GRASAS | Grasas |
| LACTEOS | Lácteos |
| LACTEOS - GRASAS | Lácteos - Grasas |
| LEGUMBRES - CARBOHIDRATOS | Legumbres - Carbohidratos |
| PROTEINA - CERDO / POLLO / RES / PAVO / PESCADO / MARISCOS / HUEVO | Proteína - (tipo) |
| SEMILLAS/FRUTOS SECOS - GRASAS | Semillas/Frutos Secos - Grasas |
| VEGETALES | Vegetales |
| VEGETALES - CARBOHIDRATOS | Vegetales - Carbohidratos |
| VEGETALES - GRASAS | Vegetales - Grasas |

### 5b. Parseo de costos
- El caracter `.` se **elimina** (es separador de miles en notación colombiana)
- El caracter `,` se **reemplaza** por `.` (sería separador decimal en notación colombiana, aunque ningún dato lo usó)
- Valores vacíos → `0`

### 5c. Normalización de nombres
- Se recortan espacios al inicio/final
- Se preservan acentos y caracteres especiales (Ñ, ó, etc.)
- No se aplicó stemming ni traducción

### 5d. Manejo de duplicados
- `resolution=merge-duplicates` permite re-ejecutar el script sin generar duplicados
- La clave única es `name` en `ingredient_table`

---

## 6. Herramientas Utilizadas

| Herramienta | Propósito |
|---|---|
| **Python 3 + requests** (script `load_ingredients.py`) | Parseo de TSV y envío batch a Supabase REST API |
| **Flask** (`api/index.py`) | Backend web; rutas de ingesta individual desde UI |
| **Supabase Dashboard** (SQL Editor) | Creación manual de tablas y migraciones cuando el Management API no estaba disponible |
| **Git + GitHub** | Control de versiones y despliegue a Vercel |
| **Vercel** | Hosting serverless del backend Flask |

### Script de carga (`load_ingredients.py`)
- **78 líneas** de Python
- Funciones: `parse_price()` (limpia formato colombiano), `guess_measure()` (infiere unidad desde presentación)
- Envía POST por cada fila con 100ms de separación para evitar rate limiting
- Imprime status por cada ingrediente (`OK` o `ERR` con código y mensaje)

---

## 7. Consideraciones de Ejecución

### Despliegue continuo
- Cada commit a `main` se despliega automáticamente en Vercel
- URL de producción: `https://inventory-tracker-final-project.vercel.app`
- No se requiere reinicio manual de la base de datos

### Seguridad
- Service Role Key usada solo en scripts de carga locales
- En producción, el backend usa el `anon key` con políticas RLS (Row Level Security)
- Las sesiones de usuario se autentican contra Supabase Auth (`gotrue`)

---

## 8. Estado Actual

| Componente | Estado |
|---|---|
| Base de datos | Supabase PostgreSQL operativa |
| Ingredientes | ~343 registros (completo) |
| Recetas (menú) | ~101 platos cargados |
| Costeo automático | Funcional con fallback a ingredient_table |
| Nutrición por plato | Campos disponibles, datos cargados |
| UI de ingredientes | CRUD completo + export CSV |
| UI de menú | Kanban drag & drop + editor de recetas modal |
| Analítica | Panel con gráficos (Chart.js) conectado a datos reales |
| Autenticación | Bypass temporal (demo session automática) |
| Administración | Panel de usuarios con roles |

---

*Documento generado el 17 de junio de 2026*
