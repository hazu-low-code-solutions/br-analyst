---
name: extract-data
description: "Ejecuta queries SQL contra el warehouse de Databricks para obtener los datos del Business Review (tabla prod_etl.gold.vima_dashboard_daily) que alimentan el análisis."
version: 0.1.0
metadata:
  hermes:
    category: datos
    tags: [databricks, sql, datos, extraccion, vima]
    requires_toolsets: [terminal]
required_environment_variables:
  - name: DATABRICKS_TOKEN
    prompt: "Token de acceso personal de Databricks"
    help: "https://docs.databricks.com/en/dev-tools/auth/pat.html"
    required_for: "Autenticar contra el workspace de Databricks"
  - name: DATABRICKS_HOST
    prompt: "URL del workspace de Databricks (ej: https://adb-xxxx.azuredatabricks.net)"
    required_for: "Conectar al workspace correcto"
  - name: DATABRICKS_WAREHOUSE_ID
    prompt: "ID del SQL warehouse a usar para ejecutar las queries"
    required_for: "Ejecutar las queries SQL"
---

# Extracción de Datos — Databricks

## Cuándo usar esta skill

Úsala cada vez que necesites obtener datos crudos para el análisis del Business Review, antes de interpretar tendencias o comparar periodos. Es el único punto de acceso a la tabla `prod_etl.gold.vima_dashboard_daily` y a cualquier otra tabla del warehouse que el análisis requiera.

---

## Procedimiento

### PASO 1 — Construir la query

Define el SQL que necesitas. La tabla principal del Business Review es:

```
prod_etl.gold.vima_dashboard_daily
```

### PASO 2 — Ejecutar la extracción

Ejecuta `scripts/extract_data.py` pasando el SQL como único argumento:

```bash
python scripts/extract_data.py "SELECT * FROM prod_etl.gold.vima_dashboard_daily LIMIT 20"
```

El script imprime un único JSON en stdout con dos llaves:

| Llave | Contenido |
|---|---|
| `columns` | Lista de nombres de columna, en orden |
| `rows` | Lista de filas, cada una como arreglo de valores alineado a `columns` |

### PASO 3 — Manejar errores

Si la query falla, el script termina con código de salida distinto de cero y un mensaje `ERROR (...)` en stderr. Causas comunes:

- Credenciales ausentes o inválidas (`DATABRICKS_TOKEN`, `DATABRICKS_HOST`, `DATABRICKS_WAREHOUSE_ID`).
- El warehouse sigue `PENDING` o `RUNNING` después de 50s (warehouse apagado o sobrecargado).
- La query es inválida o la tabla referenciada no existe.

Reporta el error tal cual al usuario; no reintentes automáticamente más de una vez.

---

## Errores comunes

- **Warehouse dormido:** la primera ejecución del día puede tardar en encender el warehouse. Si el timeout de 50s no es suficiente, vuelve a intentar.
- **Esquema vacío:** si la query no retorna columnas (por ejemplo, un `INSERT` o `CREATE`), el script falla intencionalmente — esta skill es solo de lectura.
- **Variables de entorno faltantes:** revisa `.env.example` en la raíz del proyecto y confirma que `.env` tenga los tres valores configurados.

---

## Verificación rápida

```bash
cd skills/extract-data/scripts
python extract_data.py "SELECT * FROM prod_etl.gold.vima_dashboard_daily LIMIT 5"
```

Resultado esperado: `{"columns": [...], "rows": [...]}`
