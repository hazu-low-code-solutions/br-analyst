---
name: business-review
description: "Genera el PDF del Business Review mensual de VIMA. Extrae los datos de Databricks, construye las tablas del reporte y produce un PDF listo para enviar al cliente."
version: 0.1.0
metadata:
  hermes:
    category: reporte
    tags: [business-review, vima, pdf, databricks, sellout]
    requires_toolsets: [terminal]
---

# Business Review VIMA — Generación de PDF

## Cuándo usar esta skill

Úsala cada vez que el usuario pida generar el Business Review de VIMA. Frases que la activan:

- "arma el business review de VIMA"
- "genera el reporte de mayo"
- "crea el PDF del business review"
- "prepara el business review para [mes]"

---

## Procedimiento

### PASO 1 — Identificar el mes

Si el usuario especifica un mes, úsalo. Si no, el script usa por defecto **el mes anterior al actual**.

Formato esperado: `YYYY-MM` (ej: `2026-05` para mayo 2026).

### PASO 2 — Ejecutar el script

```bash
cd /Users/assef/Repos/@hazu-low-code-solutions/br-analyst
python skills/business-review/generate_report.py [YYYY-MM] [--output ruta.pdf]
```

Ejemplos:

```bash
# Mes anterior al actual (default)
python skills/business-review/generate_report.py

# Mayo 2026 explícito
python skills/business-review/generate_report.py 2026-05

# Con nombre de archivo personalizado
python skills/business-review/generate_report.py 2026-05 --output ~/Desktop/BR_VIMA_Mayo2026.pdf
```

### PASO 3 — Verificar la salida

El script imprime:
```
📊 Business Review VIMA — Mayo 2026
   yyyymm_actual=202605  yyyymm_ly=202505
   Ejecutando query en Databricks...
   10 filas obtenidas
   Generando PDF...
✅ PDF generado: /ruta/al/archivo.pdf
```

Si hay errores de credenciales o de warehouse, reporta el mensaje tal cual al usuario.

---

## Tabla generada — "Venta Mes Anterior Cadena / Formato"

El PDF contiene una tabla con estructura:

| Nivel | Descripción |
|---|---|
| Fila Retailer (negrita, fondo azul claro) | Totales agregados por cadena |
| Filas Categoría (indentadas) | Desglose por Frutas / Papa / Pescados / Smoothies / Vegetales |
| Fila Total (fondo azul oscuro) | Gran total del periodo |

**Columnas (9):**

| Columna | Tipo | Descripción |
|---|---|---|
| Ven Año Ant $ | Valor ($) | Ventas mes completo año anterior |
| Ven Año Act $ | Valor ($) | Ventas mes completo año actual |
| % Var $ | % | Variación YA en valor |
| Ven Año Ant Uni | Unidades | Unidades año anterior |
| Ven Año Act Uni | Unidades | Unidades año actual |
| % Var Uni | % | Variación YA en unidades |
| Ven Año Ant Kg | Kg | Kilos año anterior |
| Año Act Kg | Kg | Kilos año actual |
| var YA Kg% | % | Variación YA en kilos |

**Filtros activos:** `store_channel != 'Cedis'` y `category != 'OUT'`

---

## Fuente de datos

- **Query:** `rsc/measures_bible.json` → `query_patterns.table_by_retailer_categoria`
- **Tabla principal:** `prod_etl.gold.vima_dashboard_daily`
- **Tabla productos:** `prod_etl.segmentation.products` (join por `id_product_retailer`)
- **Tabla tiendas:** `prod_etl.segmentation.stores` (join por `id_store`)

---

## Dependencias

```bash
pip install reportlab databricks-sdk
```

Las credenciales se leen de las variables de entorno (ver `.env.example`). El script tiene un fallback al token de desarrollo configurado en `skills/test.py`.

---

## Errores comunes

| Error | Causa | Solución |
|---|---|---|
| `❌ Falta reportlab` | Librería no instalada | `pip install reportlab` |
| `SQL failed` | Warehouse dormido o credencial inválida | Reintentar; verificar token |
| `FileNotFoundError: measures_bible.json` | Ruta incorrecta | Ejecutar desde el directorio raíz del proyecto |
