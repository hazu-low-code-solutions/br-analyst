#!/usr/bin/env python3
"""
Business Review VIMA — genera el PDF con dos tablas:
  1. Venta Mes Anterior Cadena / Formato
  2. Venta Acumulada (Ene-XXX) Cadena / Formato

Uso:
    python generate_report.py [YYYY-MM] [--output ruta.pdf]

    YYYY-MM  Mes del reporte. Default: mes anterior al actual.
    --output Ruta del PDF. Default: business_review_YYYYMM.pdf en el directorio actual.

Credenciales (env vars o fallback hardcodeado):
    DATABRICKS_HOST          URL del workspace
    DATABRICKS_TOKEN         Personal access token
    DATABRICKS_WAREHOUSE_ID  SQL warehouse ID

Dependencias:
    pip install reportlab python-dateutil databricks-sdk
"""

import argparse
import importlib.util
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT           = Path(__file__).resolve().parents[2]
BIBLE_PATH     = ROOT / "rsc/measures_bible.json"
EXTRACT_SCRIPT = ROOT / "skills/extract-data/scripts/extract_data.py"

# ── Credenciales ──────────────────────────────────────────────────────────────
os.environ.setdefault("DATABRICKS_HOST",         "https://adb-2421265422447168.8.azuredatabricks.net")
os.environ.setdefault("DATABRICKS_WAREHOUSE_ID", "bc00e054b14469a7")

# ── Nombres de meses ──────────────────────────────────────────────────────────
MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo",    4: "Abril",
    5: "Mayo",  6: "Junio",   7: "Julio",    8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}
MESES_CORTO = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}

# ── Configuración de columnas por tabla ───────────────────────────────────────
#
# Cada config define cómo construir, sumar y formatear una tabla.
# "sum_cols"   → columnas brutas que se acumulan para totales de retailer y grand total
# "pct_keys"   → (col_resultado, col_num, col_den) — ratios calculados sobre los sums
# "col_types"  → tipo de formato por columna
# "data_cols"  → orden de columnas en la tabla (sin la col de dimensión)
# "pct_idxs"   → posiciones 1-indexed (en la tabla) de las columnas % para colorear
# "headers"    → encabezados de columna

MONTHLY_CFG = {
    "sum_cols":  ["YA_A_Valor", "CM_Valor", "YA_A_Uni", "CM_Uni", "YA_A_Kg", "CM_Kg"],
    "pct_keys":  [
        ("var_YA_Valor", "CM_Valor",  "YA_A_Valor"),
        ("var_YA_Uni",   "CM_Uni",    "YA_A_Uni"),
        ("var_YA_Kg",    "CM_Kg",     "YA_A_Kg"),
    ],
    "col_types": {
        "YA_A_Valor":  "valor", "CM_Valor":  "valor", "var_YA_Valor": "pct",
        "YA_A_Uni":    "uni",   "CM_Uni":    "uni",   "var_YA_Uni":   "pct",
        "YA_A_Kg":     "kg",    "CM_Kg":     "kg",    "var_YA_Kg":    "pct",
    },
    "data_cols": [
        "YA_A_Valor", "CM_Valor", "var_YA_Valor",
        "YA_A_Uni",   "CM_Uni",   "var_YA_Uni",
        "YA_A_Kg",    "CM_Kg",    "var_YA_Kg",
    ],
    "pct_idxs": [3, 6, 9],
    "headers": [
        "Retailer",
        "Ven Año Ant $", "Ven Año Act $", "% Var $",
        "Ven Año Ant Uni", "Ven Año Act Uni", "% Var Uni",
        "Ven Año Ant Kg", "Año Act Kg", "var YA Kg%",
    ],
}

YTD_CFG = {
    "sum_cols":  ["YTD_YA1_Valor", "YTD_Valor", "YTD_YA1_Uni", "YTD_Uni", "YTD_YA1_Kg", "YTD_Kg"],
    "pct_keys":  [
        ("YTD_vs_YA1_Valor", "YTD_Valor",  "YTD_YA1_Valor"),
        ("YTD_vs_YA1_Uni",   "YTD_Uni",    "YTD_YA1_Uni"),
        ("YTD_vs_YA1_Kg",    "YTD_Kg",     "YTD_YA1_Kg"),
    ],
    "col_types": {
        "YTD_YA1_Valor":    "valor", "YTD_Valor":    "valor", "YTD_vs_YA1_Valor": "pct",
        "YTD_YA1_Uni":      "uni",   "YTD_Uni":      "uni",   "YTD_vs_YA1_Uni":   "pct",
        "YTD_YA1_Kg":       "kg",    "YTD_Kg":       "kg",    "YTD_vs_YA1_Kg":    "pct",
    },
    "data_cols": [
        "YTD_YA1_Valor", "YTD_Valor", "YTD_vs_YA1_Valor",
        "YTD_YA1_Uni",   "YTD_Uni",   "YTD_vs_YA1_Uni",
        "YTD_YA1_Kg",    "YTD_Kg",    "YTD_vs_YA1_Kg",
    ],
    "pct_idxs": [3, 6, 9],
    "headers": [
        "Cadena",
        "Acum. Ant $", "Acum. Act $", "% var $",
        "Acum Ant Uni", "Acum Act Uni", "% var Uni",
        "Acum. Ant Kg", "Acum. Act Kg", "%Var KG",
    ],
}


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="Business Review VIMA — genera PDF")
    p.add_argument("month",    nargs="?", help="Mes del reporte YYYY-MM (default: mes anterior)")
    p.add_argument("--output", help="Ruta del PDF de salida")
    return p.parse_args()


# ── Fechas ────────────────────────────────────────────────────────────────────
def get_months(month_str=None):
    """Retorna (yyyymm_actual, yyyymm_ly, mes_date) para la tabla mensual."""
    if month_str:
        d   = datetime.strptime(month_str, "%Y-%m")
        mes = date(d.year, d.month, 1)
    else:
        today = date.today()
        mes   = date(today.year, today.month - 1, 1) if today.month > 1 else date(today.year - 1, 12, 1)

    yyyymm_actual = mes.year * 100 + mes.month
    yyyymm_ly     = yyyymm_actual - 100
    return yyyymm_actual, yyyymm_ly, mes


def get_ytd_params(yyyymm_actual, yyyymm_ly):
    """
    Deriva los 4 parámetros YTD a partir de los params mensuales.
    yyyymm_actual es el mes de cierre del YTD (= último mes completo).
    """
    year    = yyyymm_actual // 100
    year_ly = yyyymm_ly    // 100
    return {
        "ytd_start_yyyymm":    year    * 100 + 1,   # Ene año actual
        "ytd_end_yyyymm":      yyyymm_actual,        # mes cierre actual
        "ytd_start_ly_yyyymm": year_ly * 100 + 1,   # Ene año anterior
        "ytd_end_ly_yyyymm":   yyyymm_ly,            # mes cierre anterior
    }


# ── Queries ───────────────────────────────────────────────────────────────────
def build_monthly_query(yyyymm_actual, yyyymm_ly):
    bible    = json.loads(BIBLE_PATH.read_text())
    template = bible["query_patterns"]["table_by_retailer_categoria"]["template"]
    return (template
            .replace("{yyyymm_actual}", str(yyyymm_actual))
            .replace("{yyyymm_ly}",     str(yyyymm_ly)))


def build_ytd_query(ytd_params):
    bible    = json.loads(BIBLE_PATH.read_text())
    template = bible["query_patterns"]["table_by_retailer_categoria_ytd"]["template"]
    for k, v in ytd_params.items():
        template = template.replace("{" + k + "}", str(v))
    return template


def run_query(sql):
    spec = importlib.util.spec_from_file_location("extract_data", EXTRACT_SCRIPT)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run_query(sql)


# ── Formateo ──────────────────────────────────────────────────────────────────
def parse_float(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def fmt(val, col_type):
    f = parse_float(val)
    if f is None:
        return ""
    if col_type == "pct":
        sign = "+" if f > 0 else ""
        return f"{sign}{f * 100:.1f}%"
    if col_type in ("valor", "kg"):
        return f"{f:,.0f}"
    if col_type == "uni":
        return f"{int(round(f)):,}"
    return str(val)


# ── Agrupación y totales (genérico) ───────────────────────────────────────────
def compute_totals(cat_rows, cfg):
    sums = defaultdict(lambda: None)
    for row in cat_rows:
        for col in cfg["sum_cols"]:
            v = parse_float(row.get(col))
            if v is not None:
                sums[col] = (sums[col] or 0.0) + v

    for pct_col, num_col, den_col in cfg["pct_keys"]:
        n, d = sums.get(num_col), sums.get(den_col)
        sums[pct_col] = (n / d - 1) if (n is not None and d) else None

    return dict(sums)


def build_display_rows(result, cfg):
    cols = result["columns"]
    rows = [dict(zip(cols, r)) for r in result["rows"]]

    retailer_order, retailer_map = [], {}
    for row in rows:
        r = row["retailer"]
        if r not in retailer_map:
            retailer_map[r] = []
            retailer_order.append(r)
        retailer_map[r].append(row)

    display  = []
    all_rows = []

    for retailer in retailer_order:
        cat_rows = retailer_map[retailer]
        totals   = compute_totals(cat_rows, cfg)
        display.append({"type": "retailer", "label": retailer, **totals})
        for row in cat_rows:
            display.append({
                "type":  "categoria",
                "label": row["categoria"],
                **{k: row.get(k) for k in cfg["col_types"]},
            })
        all_rows.extend(cat_rows)

    grand = compute_totals(all_rows, cfg)
    display.append({"type": "total", "label": "Total", **grand})
    return display


# ── Construcción de tabla ReportLab (reutilizable) ────────────────────────────
def _build_rl_table(display_rows, cfg, colors_mod):
    from reportlab.platypus import Table, TableStyle

    AZUL    = colors_mod.HexColor("#2B5278")
    AZUL_LT = colors_mod.HexColor("#D0DEF0")
    GRIS1   = colors_mod.HexColor("#F5F5F0")
    VERDE   = colors_mod.HexColor("#1A7A3C")
    ROJO    = colors_mod.HexColor("#C0392B")

    table_data     = [cfg["headers"]]
    retailer_idxs  = []
    categoria_idxs = []
    total_idxs     = []

    for i, row in enumerate(display_rows):
        values = [fmt(row.get(col), cfg["col_types"][col]) for col in cfg["data_cols"]]
        table_data.append([row["label"]] + values)
        ri = i + 1
        if row["type"] == "retailer":
            retailer_idxs.append(ri)
        elif row["type"] == "categoria":
            categoria_idxs.append(ri)
        elif row["type"] == "total":
            total_idxs.append(ri)

    from reportlab.lib.units import cm
    col_widths = [4.2 * cm] + [2.45 * cm] * 9
    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    cmds = [
        ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  colors_mod.white),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, 0),  7),
        ("ALIGN",          (0, 0), (-1, 0),  "CENTER"),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE",       (0, 1), (-1, -1), 8),
        ("ALIGN",          (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN",          (0, 1), (0, -1),  "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [GRIS1, colors_mod.white]),
        ("GRID",           (0, 0), (-1, -1), 0.25, colors_mod.HexColor("#CCCCCC")),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
    ]

    for idx in retailer_idxs:
        cmds += [
            ("FONTNAME",   (0, idx), (-1, idx), "Helvetica-Bold"),
            ("BACKGROUND", (0, idx), (-1, idx), AZUL_LT),
        ]
    for idx in categoria_idxs:
        cmds.append(("LEFTPADDING", (0, idx), (0, idx), 18))
    for idx in total_idxs:
        cmds += [
            ("FONTNAME",   (0, idx), (-1, idx), "Helvetica-Bold"),
            ("BACKGROUND", (0, idx), (-1, idx), AZUL),
            ("TEXTCOLOR",  (0, idx), (-1, idx), colors_mod.white),
        ]

    pct_col_names = [cfg["data_cols"][ci - 1] for ci in cfg["pct_idxs"]]
    for i, row in enumerate(display_rows):
        for ci, col_name in zip(cfg["pct_idxs"], pct_col_names):
            v = parse_float(row.get(col_name))
            if v is not None:
                color = VERDE if v >= 0 else ROJO
                cmds.append(("TEXTCOLOR", (ci, i + 1), (ci, i + 1), color))

    table.setStyle(TableStyle(cmds))
    return table


# ── PDF ───────────────────────────────────────────────────────────────────────
def generate_pdf(monthly_rows, ytd_rows, mes_nombre, mes_corto, anio, output_path):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        sys.exit("❌ Falta reportlab. Instala con: pip install reportlab")

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        rightMargin=1 * cm, leftMargin=1 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )

    styles      = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Normal"],
                                  fontSize=13, fontName="Helvetica-Bold",
                                  alignment=1, spaceAfter=3)
    sub_style   = ParagraphStyle("sub", parent=styles["Normal"],
                                  fontSize=9, alignment=1, spaceAfter=10)

    story = [
        # ── Tabla 1: Mensual ──────────────────────────────────────────────────
        Paragraph("Venta Mes Anterior Cadena / Formato", title_style),
        Paragraph(f"(Mes Anterior {mes_nombre} {anio})", sub_style),
        _build_rl_table(monthly_rows, MONTHLY_CFG, colors),
        PageBreak(),
        # ── Tabla 2: YTD ─────────────────────────────────────────────────────
        Paragraph(f"Venta Acumulada (Ene-{mes_corto}) Cadena / Formato", title_style),
        Paragraph(f"(Acumulado Enero–{mes_nombre} {anio})", sub_style),
        _build_rl_table(ytd_rows, YTD_CFG, colors),
    ]

    doc.build(story)
    print(f"✅ PDF generado: {output_path.resolve()}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    yyyymm_actual, yyyymm_ly, mes = get_months(args.month)
    mes_nombre = MESES_ES[mes.month]
    mes_corto  = MESES_CORTO[mes.month]
    output     = Path(args.output) if args.output else Path(f"business_review_{yyyymm_actual}.pdf")

    print(f"📊 Business Review VIMA — {mes_nombre} {mes.year}")
    print(f"   Mensual:  yyyymm_actual={yyyymm_actual}  yyyymm_ly={yyyymm_ly}")

    ytd = get_ytd_params(yyyymm_actual, yyyymm_ly)
    print(f"   YTD:      {ytd['ytd_start_yyyymm']}–{ytd['ytd_end_yyyymm']}  vs  {ytd['ytd_start_ly_yyyymm']}–{ytd['ytd_end_ly_yyyymm']}")

    print("   [1/2] Query mensual...")
    monthly_sql  = build_monthly_query(yyyymm_actual, yyyymm_ly)
    monthly_data = run_query(monthly_sql)
    print(f"         {len(monthly_data['rows'])} filas")

    print("   [2/2] Query YTD...")
    ytd_sql  = build_ytd_query(ytd)
    ytd_data = run_query(ytd_sql)
    print(f"         {len(ytd_data['rows'])} filas")

    monthly_rows = build_display_rows(monthly_data, MONTHLY_CFG)
    ytd_rows     = build_display_rows(ytd_data,     YTD_CFG)

    print("   Generando PDF...")
    generate_pdf(monthly_rows, ytd_rows, mes_nombre, mes_corto, mes.year, output)


if __name__ == "__main__":
    main()
