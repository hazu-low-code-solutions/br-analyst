#!/usr/bin/env python3
"""
Business Review VIMA — genera el PDF de "Venta Mes Anterior Cadena / Formato".

Uso:
    python generate_report.py [YYYY-MM] [--output ruta.pdf]

    YYYY-MM  Mes del reporte. Default: mes anterior al actual.
    --output Ruta del PDF. Default: business_review_YYYYMM.pdf en el directorio actual.

Credenciales (env vars o fallback al token de skills/test.py):
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

# ── Credenciales: env vars ──────────────────────────────────────────────────
os.environ.setdefault("DATABRICKS_HOST",         "https://adb-2421265422447168.8.azuredatabricks.net")
os.environ.setdefault("DATABRICKS_WAREHOUSE_ID", "bc00e054b14469a7")

# ── Constantes ───────────────────────────────────────────────────────────────
MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo",    4: "Abril",
    5: "Mayo",  6: "Junio",   7: "Julio",    8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

COL_TYPES = {
    "YA_A_Valor":  "valor", "CM_Valor":  "valor", "var_YA_Valor": "pct",
    "YA_A_Uni":    "uni",   "CM_Uni":    "uni",   "var_YA_Uni":   "pct",
    "YA_A_Kg":     "kg",    "CM_Kg":     "kg",    "var_YA_Kg":    "pct",
}

DATA_COLS = [
    "YA_A_Valor", "CM_Valor", "var_YA_Valor",
    "YA_A_Uni",   "CM_Uni",   "var_YA_Uni",
    "YA_A_Kg",    "CM_Kg",    "var_YA_Kg",
]

HEADERS = [
    "Retailer",
    "Ven Año Ant $", "Ven Año Act $", "% Var $",
    "Ven Año Ant Uni", "Ven Año Act Uni", "% Var Uni",
    "Ven Año Ant Kg", "Año Act Kg", "var YA Kg%",
]


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="Business Review VIMA — genera PDF")
    p.add_argument("month",    nargs="?", help="Mes del reporte YYYY-MM (default: mes anterior)")
    p.add_argument("--output", help="Ruta del PDF de salida")
    return p.parse_args()


# ── Fechas ────────────────────────────────────────────────────────────────────
def get_months(month_str=None):
    if month_str:
        d   = datetime.strptime(month_str, "%Y-%m")
        mes = date(d.year, d.month, 1)
    else:
        today = date.today()
        if today.month == 1:
            mes = date(today.year - 1, 12, 1)
        else:
            mes = date(today.year, today.month - 1, 1)

    yyyymm_actual = mes.year * 100 + mes.month
    yyyymm_ly     = yyyymm_actual - 100
    return yyyymm_actual, yyyymm_ly, mes


# ── Query ─────────────────────────────────────────────────────────────────────
def build_query(yyyymm_actual, yyyymm_ly):
    bible    = json.loads(BIBLE_PATH.read_text())
    template = bible["query_patterns"]["table_by_retailer_categoria"]["template"]
    return (template
            .replace("{yyyymm_actual}", str(yyyymm_actual))
            .replace("{yyyymm_ly}",     str(yyyymm_ly)))


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


# ── Agrupación y totales ──────────────────────────────────────────────────────
SUM_COLS = ["YA_A_Valor", "CM_Valor", "YA_A_Uni", "CM_Uni", "YA_A_Kg", "CM_Kg"]


def compute_totals(cat_rows):
    sums = defaultdict(lambda: None)
    for row in cat_rows:
        for col in SUM_COLS:
            v = parse_float(row.get(col))
            if v is not None:
                sums[col] = (sums[col] or 0.0) + v

    def pct(num_k, den_k):
        n, d = sums.get(num_k), sums.get(den_k)
        return (n / d - 1) if (n is not None and d) else None

    sums["var_YA_Valor"] = pct("CM_Valor", "YA_A_Valor")
    sums["var_YA_Uni"]   = pct("CM_Uni",   "YA_A_Uni")
    sums["var_YA_Kg"]    = pct("CM_Kg",    "YA_A_Kg")
    return dict(sums)


def build_display_rows(result):
    cols = result["columns"]
    rows = [dict(zip(cols, r)) for r in result["rows"]]

    # Mantener orden de aparición de retailers
    retailer_order = []
    retailer_map   = {}
    for row in rows:
        r = row["retailer"]
        if r not in retailer_map:
            retailer_map[r] = []
            retailer_order.append(r)
        retailer_map[r].append(row)

    display = []
    all_rows = []

    for retailer in retailer_order:
        cat_rows = retailer_map[retailer]
        totals   = compute_totals(cat_rows)

        display.append({"type": "retailer", "label": retailer, **totals})

        for row in cat_rows:
            display.append({
                "type":  "categoria",
                "label": row["categoria"],
                **{k: row.get(k) for k in COL_TYPES},
            })

        all_rows.extend(cat_rows)

    grand = compute_totals(all_rows)
    display.append({"type": "total", "label": "Total", **grand})
    return display


# ── PDF ───────────────────────────────────────────────────────────────────────
def generate_pdf(display_rows, mes_nombre, anio, output_path):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                        Table, TableStyle)
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

    # ── Construir datos de tabla ──────────────────────────────────────────────
    table_data     = [HEADERS]
    retailer_idxs  = []
    categoria_idxs = []
    total_idxs     = []

    for i, row in enumerate(display_rows):
        values     = [fmt(row.get(col), COL_TYPES[col]) for col in DATA_COLS]
        table_data.append([row["label"]] + values)
        ri = i + 1  # offset por header
        if row["type"] == "retailer":
            retailer_idxs.append(ri)
        elif row["type"] == "categoria":
            categoria_idxs.append(ri)
        elif row["type"] == "total":
            total_idxs.append(ri)

    col_widths = [4.2 * cm] + [2.45 * cm] * 9

    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    AZUL    = colors.HexColor("#2B5278")
    AZUL_LT = colors.HexColor("#D0DEF0")
    GRIS1   = colors.HexColor("#F5F5F0")
    VERDE   = colors.HexColor("#1A7A3C")
    ROJO    = colors.HexColor("#C0392B")

    cmds = [
        # Header
        ("BACKGROUND",   (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),  7),
        ("ALIGN",        (0, 0), (-1, 0),  "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        # Body
        ("FONTSIZE",     (0, 1), (-1, -1), 8),
        ("ALIGN",        (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN",        (0, 1), (0, -1),  "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [GRIS1, colors.white]),
        ("GRID",         (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]

    # Retailer rows — bold + fondo azul claro
    for idx in retailer_idxs:
        cmds += [
            ("FONTNAME",   (0, idx), (-1, idx), "Helvetica-Bold"),
            ("BACKGROUND", (0, idx), (-1, idx), AZUL_LT),
        ]

    # Categoría — indent
    for idx in categoria_idxs:
        cmds.append(("LEFTPADDING", (0, idx), (0, idx), 18))

    # Total — bold + fondo azul oscuro
    for idx in total_idxs:
        cmds += [
            ("FONTNAME",   (0, idx), (-1, idx), "Helvetica-Bold"),
            ("BACKGROUND", (0, idx), (-1, idx), AZUL),
            ("TEXTCOLOR",  (0, idx), (-1, idx), colors.white),
        ]

    # Color en columnas %: verde positivo, rojo negativo
    PCT_COL_IDXS = [3, 6, 9]  # posiciones 1-indexed de var_YA_Valor, _Uni, _Kg
    for i, row in enumerate(display_rows):
        for ci, col_name in zip(PCT_COL_IDXS, ["var_YA_Valor", "var_YA_Uni", "var_YA_Kg"]):
            v = parse_float(row.get(col_name))
            if v is not None:
                color = VERDE if v >= 0 else ROJO
                cmds.append(("TEXTCOLOR", (ci, i + 1), (ci, i + 1), color))

    table.setStyle(TableStyle(cmds))

    doc.build([
        Paragraph("Venta Mes Anterior Cadena / Formato", title_style),
        Paragraph(f"(Mes Anterior {mes_nombre} {anio})", sub_style),
        table,
    ])

    print(f"✅ PDF generado: {output_path.resolve()}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    yyyymm_actual, yyyymm_ly, mes = get_months(args.month)
    mes_nombre = MESES_ES[mes.month]
    output     = Path(args.output) if args.output else Path(f"business_review_{yyyymm_actual}.pdf")

    print(f"📊 Business Review VIMA — {mes_nombre} {mes.year}")
    print(f"   yyyymm_actual={yyyymm_actual}  yyyymm_ly={yyyymm_ly}")
    print("   Ejecutando query en Databricks...")

    sql    = build_query(yyyymm_actual, yyyymm_ly)
    result = run_query(sql)
    print(f"   {len(result['rows'])} filas obtenidas")

    display_rows = build_display_rows(result)

    print("   Generando PDF...")
    generate_pdf(display_rows, mes_nombre, mes.year, output)


if __name__ == "__main__":
    main()
