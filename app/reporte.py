"""Reporte de ventas en Excel, generado en el momento de descargarlo.

Hojas: Resumen, Por día, Por semana, Por mes, Productos, Fiados, Ventas, Abonos, Detalle e Inventario.
Los totales son fórmulas de Excel (SUMIFS, COUNTIFS...) que leen la hoja Ventas, así
que si alguien corrige un dato el reporte se recalcula. Además cada fórmula lleva su
resultado ya calculado, para que se vea bien en el celular aunque el visor no calcule.
"""

from __future__ import annotations

import io
from collections import defaultdict
from datetime import date, datetime, timedelta

import xlsxwriter

from .servicios import Tienda
from .utils import ahora

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
VALIDA, ANULADA = "Válida", "Anulada"


def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _nombre_mes(clave: str) -> str:
    anio, mes = clave.split("-")
    return f"{MESES[int(mes) - 1].capitalize()} {anio}"


def generar_excel(tienda: Tienda) -> bytes:
    con = tienda.con
    hoy = ahora().date()

    # ------------------------------------------------------------ datos
    ventas = []
    for f in con.execute(
            "SELECT v.*, COALESCE(u.nombre, '') AS vendedor FROM ventas v"
            " LEFT JOIN usuarios u ON u.id = v.usuario_id ORDER BY v.fecha, v.hora, v.id"):
        d = date.fromisoformat(f["fecha"])
        ventas.append({
            "id": f["id"], "fecha": d, "hora": f["hora"], "dia": DIAS[d.weekday()],
            "semana": _lunes(d), "mes": f["fecha"][:7], "vendedor": f["vendedor"],
            "metodo": f["metodo"], "total": f["total"] / 100, "costo": f["costo_total"] / 100,
            "estado": ANULADA if f["anulada"] else VALIDA, "productos": "", "unidades": 0,
        })
    por_id = {v["id"]: v for v in ventas}
    for f in con.execute("SELECT id, cliente_id, (SELECT nombre FROM clientes WHERE id = ventas.cliente_id) AS cliente FROM ventas"):
        if f["id"] in por_id:
            por_id[f["id"]]["cliente"] = f["cliente"] or ""
    abonos = []
    for f in con.execute(
            "SELECT a.*, c.nombre AS cliente, COALESCE(u.nombre, '') AS usuario FROM abonos a"
            " JOIN clientes c ON c.id = a.cliente_id LEFT JOIN usuarios u ON u.id = a.usuario_id"
            " ORDER BY a.fecha, a.hora, a.id"):
        d = date.fromisoformat(f["fecha"])
        abonos.append({"id": f["id"], "fecha": d, "hora": f["hora"], "semana": _lunes(d), "mes": f["fecha"][:7],
                       "cliente": f["cliente"], "metodo": f["metodo"], "monto": f["monto"] / 100,
                       "usuario": f["usuario"], "estado": ANULADA if f["anulado"] else VALIDA})
    clientes = tienda.clientes()
    detalle = []
    for f in con.execute("SELECT * FROM venta_items ORDER BY venta_id, id"):
        v = por_id.get(f["venta_id"])
        if v is None:
            continue
        v["productos"] += (", " if v["productos"] else "") + f"{f['cantidad']}× {f['nombre']}"
        v["unidades"] += f["cantidad"]
        detalle.append({"venta": v["id"], "fecha": v["fecha"], "producto": f["nombre"],
                        "cantidad": f["cantidad"], "precio": f["precio"] / 100,
                        "costo": f["costo"] / 100, "estado": v["estado"]})
    inventario = tienda.productos()
    validas = [v for v in ventas if v["estado"] == VALIDA]

    # ------------------------------------------------------------ formato
    salida = io.BytesIO()
    libro = xlsxwriter.Workbook(salida, {"in_memory": True, "default_date_format": "dd/mm/yyyy"})
    libro.set_properties({"title": "Stop 44 · Reporte de ventas", "author": "Stop 44"})
    base = {"font_name": "Arial", "font_size": 10, "valign": "vcenter"}
    fmt = {
        "titulo": libro.add_format({**base, "bold": True, "font_size": 16, "font_color": "#D21F2B"}),
        "nota": libro.add_format({**base, "italic": True, "font_color": "#6D6D68"}),
        "cabecera": libro.add_format({**base, "bold": True, "font_color": "#FFFFFF", "bg_color": "#000000",
                                      "border": 1, "text_wrap": True, "align": "center"}),
        "texto": libro.add_format({**base, "border": 1, "border_color": "#D9D9D9"}),
        "fecha": libro.add_format({**base, "border": 1, "border_color": "#D9D9D9", "num_format": "dd/mm/yyyy", "align": "left"}),
        "entero": libro.add_format({**base, "border": 1, "border_color": "#D9D9D9", "num_format": "0"}),
        "dinero": libro.add_format({**base, "border": 1, "border_color": "#D9D9D9", "num_format": "$#,##0.00;-$#,##0.00;-"}),
        "anulada": libro.add_format({**base, "border": 1, "border_color": "#D9D9D9", "font_color": "#B3261E", "font_strikeout": True}),
        "total_txt": libro.add_format({**base, "bold": True, "top": 2, "bg_color": "#F2F2F2"}),
        "total_ent": libro.add_format({**base, "bold": True, "top": 2, "bg_color": "#F2F2F2", "num_format": "0"}),
        "total_din": libro.add_format({**base, "bold": True, "top": 2, "bg_color": "#F2F2F2", "num_format": "$#,##0.00;-$#,##0.00;-"}),
        "etiqueta": libro.add_format({**base, "bold": True, "border": 1, "border_color": "#D9D9D9"}),
        "grande": libro.add_format({**base, "bold": True, "font_size": 12, "border": 1, "border_color": "#D9D9D9", "num_format": "$#,##0.00;-$#,##0.00;-"}),
        "grande_ent": libro.add_format({**base, "bold": True, "font_size": 12, "border": 1, "border_color": "#D9D9D9", "num_format": "0"}),
        "alerta": libro.add_format({**base, "border": 1, "border_color": "#D9D9D9", "bold": True, "font_color": "#B3261E"}),
    }

    def tabla(hoja, cabeceras: list[tuple[str, int]], fila: int = 0):
        for c, (nombre, ancho) in enumerate(cabeceras):
            hoja.write(fila, c, nombre, fmt["cabecera"])
            hoja.set_column(c, c, ancho)
        hoja.set_row(fila, 30)
        hoja.freeze_panes(fila + 1, 0)

    # Las hojas se crean en el orden en que se ven; se llenan después porque se citan entre sí
    h_res = libro.add_worksheet("Resumen")
    h_dia = libro.add_worksheet("Por día")
    h_sem = libro.add_worksheet("Por semana")
    h_mes = libro.add_worksheet("Por mes")
    h_prod = libro.add_worksheet("Productos")
    h_fia = libro.add_worksheet("Fiados")
    h_ven = libro.add_worksheet("Ventas")
    h_abo = libro.add_worksheet("Abonos")
    h_det = libro.add_worksheet("Detalle")
    h_inv = libro.add_worksheet("Inventario")

    # ------------------------------------------------------------ Ventas (los datos base)
    tabla(h_ven, [("N° venta", 9), ("Fecha", 11), ("Hora", 7), ("Día", 11), ("Semana (lunes)", 13),
                  ("Mes", 9), ("Vendedor", 16), ("Método", 10), ("Productos", 48), ("Unidades", 9),
                  ("Total", 11), ("Costo", 11), ("Ganancia", 11), ("Estado", 9), ("Cliente (fiado)", 18)])
    for i, v in enumerate(ventas, start=1):
        r = i + 1                                   # fila de Excel (1 = cabecera)
        t = fmt["anulada"] if v["estado"] == ANULADA else fmt["texto"]
        h_ven.write_number(i, 0, v["id"], fmt["entero"])
        h_ven.write_datetime(i, 1, datetime.combine(v["fecha"], datetime.min.time()), fmt["fecha"])
        h_ven.write(i, 2, v["hora"], fmt["texto"])
        h_ven.write(i, 3, v["dia"], fmt["texto"])
        h_ven.write_datetime(i, 4, datetime.combine(v["semana"], datetime.min.time()), fmt["fecha"])
        h_ven.write(i, 5, v["mes"], fmt["texto"])
        h_ven.write(i, 6, v["vendedor"], fmt["texto"])
        h_ven.write(i, 7, v["metodo"], fmt["texto"])
        h_ven.write(i, 8, v["productos"], t)
        h_ven.write_number(i, 9, v["unidades"], fmt["entero"])
        h_ven.write_number(i, 10, v["total"], fmt["dinero"])
        h_ven.write_number(i, 11, v["costo"], fmt["dinero"])
        h_ven.write_formula(i, 12, f"=K{r}-L{r}", fmt["dinero"], round(v["total"] - v["costo"], 2))
        h_ven.write(i, 13, v["estado"], t)
        h_ven.write(i, 14, v.get("cliente", ""), fmt["texto"])
    if ventas:
        h_ven.autofilter(0, 0, len(ventas), 14)

    # ------------------------------------------------------------ Abonos (pagos de fiados)
    tabla(h_abo, [("N° abono", 9), ("Fecha", 11), ("Hora", 7), ("Semana (lunes)", 13), ("Mes", 9),
                  ("Cliente", 22), ("Método", 10), ("Monto", 11), ("Recibió", 16), ("Estado", 9)])
    for i, a in enumerate(abonos, start=1):
        h_abo.write_number(i, 0, a["id"], fmt["entero"])
        h_abo.write_datetime(i, 1, datetime.combine(a["fecha"], datetime.min.time()), fmt["fecha"])
        h_abo.write(i, 2, a["hora"], fmt["texto"])
        h_abo.write_datetime(i, 3, datetime.combine(a["semana"], datetime.min.time()), fmt["fecha"])
        h_abo.write(i, 4, a["mes"], fmt["texto"])
        h_abo.write(i, 5, a["cliente"], fmt["anulada"] if a["estado"] == ANULADA else fmt["texto"])
        h_abo.write(i, 6, a["metodo"], fmt["texto"])
        h_abo.write_number(i, 7, a["monto"], fmt["dinero"])
        h_abo.write(i, 8, a["usuario"], fmt["texto"])
        h_abo.write(i, 9, a["estado"], fmt["texto"])
    if abonos:
        h_abo.autofilter(0, 0, len(abonos), 9)
    na = max(len(abonos), 1) + 1
    A = {k: f"Abonos!${c}$2:${c}${na}" for k, c in [("fecha", "B"), ("semana", "D"), ("mes", "E"), ("cliente", "F"),
                                                    ("monto", "H"), ("estado", "J")]}
    abonos_validos = [a for a in abonos if a["estado"] == VALIDA]

    # rangos que usan las fórmulas (hasta la última fila de datos)
    n = max(len(ventas), 1) + 1
    V = {k: f"Ventas!${c}$2:${c}${n}" for k, c in
         [("fecha", "B"), ("semana", "E"), ("mes", "F"), ("metodo", "H"), ("total", "K"),
          ("ganancia", "M"), ("estado", "N")]}

    def resumen_de(lista, abonos_lista=()):
        por = lambda m: round(sum(v["total"] for v in lista if v["metodo"] == m), 2)
        tot = sum(v["total"] for v in lista)
        return {"n": len(lista), "ef": por("Efectivo"), "de": por("Deuna"), "fi": por("Fiado"), "tot": round(tot, 2),
                "gan": round(sum(v["total"] - v["costo"] for v in lista), 2),
                "ab": round(sum(a["monto"] for a in abonos_lista), 2)}

    def hoja_periodo(hoja, titulo_clave, ancho_clave, claves, criterio, escribir_clave, agrupar):
        """Una fila por periodo: ventas, efectivo, Deuna, fiado, total, ganancia, promedio y abonos."""
        tabla(hoja, [(titulo_clave, ancho_clave), ("Detalle", 22), ("Ventas", 8), ("Efectivo", 12),
                     ("Deuna", 12), ("Fiado", 12), ("Total", 12), ("Ganancia", 12), ("Venta promedio", 12),
                     ("Abonos de fiados cobrados", 13)])
        grupos, grupos_ab = defaultdict(list), defaultdict(list)
        for v in validas:
            grupos[agrupar(v)].append(v)
        for a in abonos_validos:
            grupos_ab[agrupar(a)].append(a)
        for i, clave in enumerate(claves, start=1):
            r = i + 1
            s = resumen_de(grupos.get(clave, []), grupos_ab.get(clave, []))
            escribir_clave(hoja, i, clave)
            c = f'{V[criterio]},$A{r},{V["estado"]},"{VALIDA}"'
            hoja.write_formula(i, 2, f"=COUNTIFS({c})", fmt["entero"], s["n"])
            hoja.write_formula(i, 3, f'=SUMIFS({V["total"]},{c},{V["metodo"]},"Efectivo")', fmt["dinero"], s["ef"])
            hoja.write_formula(i, 4, f'=SUMIFS({V["total"]},{c},{V["metodo"]},"Deuna")', fmt["dinero"], s["de"])
            hoja.write_formula(i, 5, f'=SUMIFS({V["total"]},{c},{V["metodo"]},"Fiado")', fmt["dinero"], s["fi"])
            hoja.write_formula(i, 6, f"=D{r}+E{r}+F{r}", fmt["dinero"], s["tot"])
            hoja.write_formula(i, 7, f'=SUMIFS({V["ganancia"]},{c})', fmt["dinero"], s["gan"])
            hoja.write_formula(i, 8, f"=IF(C{r}>0,G{r}/C{r},0)", fmt["dinero"], s["tot"] / s["n"] if s["n"] else 0)
            hoja.write_formula(i, 9, f'=SUMIFS({A["monto"]},{A[criterio]},$A{r},{A["estado"]},"{VALIDA}")',
                               fmt["dinero"], s["ab"])
        fin = len(claves) + 1
        total = resumen_de(validas, abonos_validos)
        hoja.write(fin, 0, "Total", fmt["total_txt"])
        hoja.write(fin, 1, "", fmt["total_txt"])
        for col, letra, valor, f_ in [(2, "C", total["n"], "total_ent"), (3, "D", total["ef"], "total_din"),
                                      (4, "E", total["de"], "total_din"), (5, "F", total["fi"], "total_din"),
                                      (6, "G", total["tot"], "total_din"), (7, "H", total["gan"], "total_din"),
                                      (9, "J", total["ab"], "total_din")]:
            hoja.write_formula(fin, col, f"=SUM({letra}2:{letra}{fin})" if claves else "=0", fmt[f_], valor)
        hoja.write_formula(fin, 8, f"=IF(C{fin + 1}>0,G{fin + 1}/C{fin + 1},0)", fmt["total_din"],
                           total["tot"] / total["n"] if total["n"] else 0)

    # Por día: todos los días desde la primera venta hasta hoy (los días sin ventas también, en cero)
    inicio = ventas[0]["fecha"] if ventas else hoy
    dias = [hoy - timedelta(days=k) for k in range((hoy - inicio).days + 1)]          # el más nuevo arriba

    def escribir_dia(hoja, i, d):
        hoja.write_datetime(i, 0, datetime.combine(d, datetime.min.time()), fmt["fecha"])
        hoja.write(i, 1, DIAS[d.weekday()].capitalize() + (" (hoy)" if d == hoy else ""), fmt["texto"])
    hoja_periodo(h_dia, "Fecha", 12, dias, "fecha", escribir_dia, lambda v: v["fecha"])

    semanas = sorted({_lunes(d) for d in dias}, reverse=True)

    def escribir_semana(hoja, i, lunes):
        hoja.write_datetime(i, 0, datetime.combine(lunes, datetime.min.time()), fmt["fecha"])
        domingo = lunes + timedelta(days=6)
        hoja.write(i, 1, f"{lunes:%d/%m} al {domingo:%d/%m/%Y}" + (" (esta semana)" if lunes == _lunes(hoy) else ""), fmt["texto"])
    hoja_periodo(h_sem, "Semana (lunes)", 13, semanas, "semana", escribir_semana, lambda v: v["semana"])

    meses = sorted({d.isoformat()[:7] for d in dias}, reverse=True)

    def escribir_mes(hoja, i, clave):
        hoja.write(i, 0, clave, fmt["texto"])
        hoja.write(i, 1, _nombre_mes(clave), fmt["texto"])
    hoja_periodo(h_mes, "Mes", 10, meses, "mes", escribir_mes, lambda v: v["mes"])

    # ------------------------------------------------------------ Detalle (cada producto vendido)
    tabla(h_det, [("N° venta", 9), ("Fecha", 11), ("Producto", 34), ("Cantidad", 9), ("Precio", 11),
                  ("Subtotal", 11), ("Costo unidad", 11), ("Ganancia", 11), ("Estado", 9)])
    for i, d in enumerate(detalle, start=1):
        r = i + 1
        h_det.write_number(i, 0, d["venta"], fmt["entero"])
        h_det.write_datetime(i, 1, datetime.combine(d["fecha"], datetime.min.time()), fmt["fecha"])
        h_det.write(i, 2, d["producto"], fmt["anulada"] if d["estado"] == ANULADA else fmt["texto"])
        h_det.write_number(i, 3, d["cantidad"], fmt["entero"])
        h_det.write_number(i, 4, d["precio"], fmt["dinero"])
        h_det.write_formula(i, 5, f"=D{r}*E{r}", fmt["dinero"], round(d["cantidad"] * d["precio"], 2))
        h_det.write_number(i, 6, d["costo"], fmt["dinero"])
        h_det.write_formula(i, 7, f"=(E{r}-G{r})*D{r}", fmt["dinero"], round((d["precio"] - d["costo"]) * d["cantidad"], 2))
        h_det.write(i, 8, d["estado"], fmt["texto"])
    if detalle:
        h_det.autofilter(0, 0, len(detalle), 8)
    m = max(len(detalle), 1) + 1
    D = {k: f"Detalle!${c}$2:${c}${m}" for k, c in [("producto", "C"), ("cantidad", "D"), ("subtotal", "F"), ("ganancia", "H"), ("estado", "I")]}

    # ------------------------------------------------------------ Productos (lo más vendido)
    tabla(h_prod, [("Producto", 34), ("Unidades vendidas", 11), ("Vendido", 12), ("Ganancia", 12)])
    agg = defaultdict(lambda: [0, 0.0, 0.0])
    for d in detalle:
        if d["estado"] == VALIDA:
            a = agg[d["producto"]]
            a[0] += d["cantidad"]; a[1] += d["cantidad"] * d["precio"]; a[2] += (d["precio"] - d["costo"]) * d["cantidad"]
    orden = sorted(agg.items(), key=lambda kv: -kv[1][1])
    for i, (nombre, (u, vend, gan)) in enumerate(orden, start=1):
        r = i + 1
        c = f'{D["producto"]},$A{r},{D["estado"]},"{VALIDA}"'
        h_prod.write(i, 0, nombre, fmt["texto"])
        h_prod.write_formula(i, 1, f'=SUMIFS({D["cantidad"]},{c})', fmt["entero"], u)
        h_prod.write_formula(i, 2, f'=SUMIFS({D["subtotal"]},{c})', fmt["dinero"], round(vend, 2))
        h_prod.write_formula(i, 3, f'=SUMIFS({D["ganancia"]},{c})', fmt["dinero"], round(gan, 2))

    # ------------------------------------------------------------ Fiados (quién debe cuánto)
    tabla(h_fia, [("Cliente", 24), ("Teléfono", 13), ("Llevó fiado", 12), ("Ha abonado", 12), ("Debe", 12),
                  ("Último movimiento", 16)])
    c_ventas = f"Ventas!$O$2:$O${n}"
    for i, cl in enumerate(clientes, start=1):
        r = i + 1
        h_fia.write(i, 0, cl.nombre, fmt["texto"])
        h_fia.write(i, 1, cl.telefono, fmt["texto"])
        h_fia.write_formula(i, 2, f'=SUMIFS({V["total"]},{c_ventas},$A{r},{V["metodo"]},"Fiado",{V["estado"]},"{VALIDA}")',
                            fmt["dinero"], cl.fiado / 100)
        h_fia.write_formula(i, 3, f'=SUMIFS({A["monto"]},{A["cliente"]},$A{r},{A["estado"]},"{VALIDA}")',
                            fmt["dinero"], cl.abonado / 100)
        h_fia.write_formula(i, 4, f"=C{r}-D{r}", fmt["alerta"] if cl.saldo > 0 else fmt["dinero"], cl.saldo / 100)
        h_fia.write(i, 5, cl.ultimo_movimiento, fmt["texto"])
    ff = len(clientes) + 1
    h_fia.write(ff, 0, "Total por cobrar", fmt["total_txt"])
    h_fia.write(ff, 1, "", fmt["total_txt"]); h_fia.write(ff, 5, "", fmt["total_txt"])
    for col, letra, valor in [(2, "C", sum(c.fiado for c in clientes) / 100), (3, "D", sum(c.abonado for c in clientes) / 100),
                              (4, "E", sum(c.saldo for c in clientes) / 100)]:
        h_fia.write_formula(ff, col, f"=SUM({letra}2:{letra}{ff})" if clientes else "=0", fmt["total_din"], valor)
    por_cobrar_ref = f"Fiados!$E${ff + 1}"

    # ------------------------------------------------------------ Inventario (foto del momento)
    tabla(h_inv, [("Producto", 30), ("Categoría", 16), ("Presentación", 14), ("Stock", 8), ("Avisar con", 9),
                  ("Costo", 11), ("Precio", 11), ("Invertido", 12), ("Si se vende todo", 13), ("Estado", 12)])
    for i, p in enumerate(inventario, start=1):
        r = i + 1
        h_inv.write(i, 0, p.nombre, fmt["texto"])
        h_inv.write(i, 1, p.categoria, fmt["texto"])
        h_inv.write(i, 2, p.presentacion, fmt["texto"])
        h_inv.write_number(i, 3, p.stock, fmt["entero"])
        h_inv.write_number(i, 4, p.minimo, fmt["entero"])
        h_inv.write_number(i, 5, p.costo / 100, fmt["dinero"])
        h_inv.write_number(i, 6, p.precio / 100, fmt["dinero"])
        h_inv.write_formula(i, 7, f"=D{r}*F{r}", fmt["dinero"], round(p.stock * p.costo / 100, 2))
        h_inv.write_formula(i, 8, f"=D{r}*G{r}", fmt["dinero"], round(p.stock * p.precio / 100, 2))
        estado = "Agotado" if p.agotado else "Por pedir" if p.stock_bajo else "Bien"
        h_inv.write_formula(i, 9, f'=IF(D{r}<=0,"Agotado",IF(D{r}<=E{r},"Por pedir","Bien"))',
                            fmt["alerta"] if estado != "Bien" else fmt["texto"], estado)
    fi = len(inventario) + 1
    h_inv.write(fi, 0, "Total", fmt["total_txt"])
    for col in (1, 2, 4, 5, 6, 9):
        h_inv.write(fi, col, "", fmt["total_txt"])
    h_inv.write_formula(fi, 3, f"=SUM(D2:D{fi})" if inventario else "=0", fmt["total_ent"], sum(p.stock for p in inventario))
    h_inv.write_formula(fi, 7, f"=SUM(H2:H{fi})" if inventario else "=0", fmt["total_din"], round(sum(p.stock * p.costo for p in inventario) / 100, 2))
    h_inv.write_formula(fi, 8, f"=SUM(I2:I{fi})" if inventario else "=0", fmt["total_din"], round(sum(p.stock * p.precio for p in inventario) / 100, 2))

    # ------------------------------------------------------------ Resumen
    h_res.set_column(0, 0, 24); h_res.set_column(1, 1, 14); h_res.set_column(2, 4, 14)
    h_res.write(0, 0, "Stop 44 · Reporte de ventas", fmt["titulo"])
    h_res.write(1, 0, f"Generado el {ahora():%d/%m/%Y a las %H:%M} (hora de Ecuador). "
                      "Cada vez que lo descargas sale con las ventas al día.", fmt["nota"])
    h_res.write(3, 0, "Fecha de hoy", fmt["etiqueta"])
    h_res.write_datetime(3, 1, datetime.combine(hoy, datetime.min.time()), fmt["fecha"])
    h_res.write(4, 0, "Semana (desde el lunes)", fmt["etiqueta"])
    h_res.write_datetime(4, 1, datetime.combine(_lunes(hoy), datetime.min.time()), fmt["fecha"])
    h_res.write(5, 0, "Mes", fmt["etiqueta"])
    h_res.write(5, 1, hoy.isoformat()[:7], fmt["texto"])
    h_res.write_comment(3, 1, "Fechas del momento en que se descargó el reporte.", {"author": "Stop 44"})

    tabla(h_res, [("Periodo", 24), ("Ventas", 14), ("Total vendido", 14), ("Ganancia", 14), ("Venta promedio", 14)], fila=7)
    h_res.freeze_panes(0, 0)
    periodos = [
        ("Hoy", f'{V["fecha"]},$B$4', [v for v in validas if v["fecha"] == hoy]),
        ("Esta semana", f'{V["semana"]},$B$5', [v for v in validas if v["semana"] == _lunes(hoy)]),
        ("Este mes", f'{V["mes"]},$B$6', [v for v in validas if v["mes"] == hoy.isoformat()[:7]]),
        ("Desde el inicio", None, validas),
    ]
    for k, (nombre, criterio, lista) in enumerate(periodos):
        fila = 8 + k; r = fila + 1
        s = resumen_de(lista)
        c = (criterio + "," if criterio else "") + f'{V["estado"]},"{VALIDA}"'
        h_res.write(fila, 0, nombre, fmt["etiqueta"])
        h_res.write_formula(fila, 1, f"=COUNTIFS({c})", fmt["grande_ent"], s["n"])
        h_res.write_formula(fila, 2, f'=SUMIFS({V["total"]},{c})', fmt["grande"], s["tot"])
        h_res.write_formula(fila, 3, f'=SUMIFS({V["ganancia"]},{c})', fmt["grande"], s["gan"])
        h_res.write_formula(fila, 4, f"=IF(B{r}>0,C{r}/B{r},0)", fmt["grande"], s["tot"] / s["n"] if s["n"] else 0)
    h_res.write(13, 0, "Fiados por cobrar", fmt["etiqueta"])
    h_res.write_formula(13, 2, f"={por_cobrar_ref}", fmt["grande"], sum(c.saldo for c in clientes) / 100)
    h_res.write(15, 0, "Las ventas anuladas no se cuentan en ningún total. Lo fiado cuenta como vendido; lo que falta cobrar está en la hoja Fiados.", fmt["nota"])
    h_res.activate()

    libro.close()
    return salida.getvalue()
