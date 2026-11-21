"""Lógica del negocio: inventario, ventas y reportes.

La API (FastAPI) solo llama a estos métodos. Aquí no hay nada de web,
así que todo se puede probar con pytest.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import db
from .modelos import METODOS_PAGO, ItemVenta, Producto, ProductoVendido, ResumenDia, Venta
from .utils import cop, fecha_corta, normalizar, sumar_dias


class ErrorTienda(Exception):
    """Error de negocio con un mensaje listo para mostrar al usuario."""


class StockInsuficiente(ErrorTienda):
    pass


class Tienda:
    def __init__(self, ruta: str | Path | None = None):
        self.con = db.conectar(ruta)

    # ------------------------------------------------------------------ util
    def _ahora(self) -> datetime:
        return datetime.now()

    @staticmethod
    def _producto(fila: sqlite3.Row) -> Producto:
        return Producto(
            id=fila["id"], nombre=fila["nombre"], categoria=fila["categoria"],
            presentacion=fila["presentacion"], codigo=fila["codigo"],
            costo=fila["costo"], precio=fila["precio"], stock=fila["stock"],
            minimo=fila["minimo"],
        )

    def _movimiento(self, producto_id: int, tipo: str, cantidad: int,
                    stock_final: int, nota: str = "", usuario_id: int | None = None) -> None:
        self.con.execute(
            "INSERT INTO movimientos (producto_id, fecha, tipo, cantidad, stock_final, nota,"
            " usuario_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (producto_id, self._ahora().strftime("%Y-%m-%d %H:%M:%S"), tipo,
             cantidad, stock_final, nota, usuario_id),
        )

    # ------------------------------------------------------------ productos
    def productos(self, buscar: str = "", categoria: str | None = None,
                  solo_bajo: bool = False) -> list[Producto]:
        filas = self.con.execute("SELECT * FROM productos WHERE activo = 1").fetchall()
        lista = [self._producto(f) for f in filas]
        q = normalizar(buscar.strip())
        if q:
            lista = [p for p in lista if q in normalizar(
                f"{p.nombre} {p.presentacion} {p.categoria} {p.codigo or ''}")]
        if categoria:
            lista = [p for p in lista if p.categoria == categoria]
        if solo_bajo:
            lista = [p for p in lista if p.stock_bajo]
        return sorted(lista, key=lambda p: normalizar(p.nombre_completo))

    def producto(self, producto_id: int) -> Producto | None:
        f = self.con.execute(
            "SELECT * FROM productos WHERE id = ? AND activo = 1", (producto_id,)).fetchone()
        return self._producto(f) if f else None

    def por_codigo(self, codigo: str) -> Producto | None:
        f = self.con.execute(
            "SELECT * FROM productos WHERE codigo = ? AND activo = 1", (codigo.strip(),)).fetchone()
        return self._producto(f) if f else None

    def guardar_producto(self, p: Producto, usuario_id: int | None = None) -> Producto:
        """Crea el producto si no tiene id, o lo actualiza."""
        p.nombre = p.nombre.strip()
        p.codigo = (p.codigo or "").strip() or None
        if not p.nombre:
            raise ErrorTienda("El producto necesita un nombre.")
        if p.precio <= 0:
            raise ErrorTienda("El precio de venta debe ser mayor que cero.")
        if p.stock < 0 or p.costo < 0 or p.minimo < 0:
            raise ErrorTienda("Costo, stock y mínimo no pueden ser negativos.")
        if p.codigo:
            otro = self.con.execute(
                "SELECT id FROM productos WHERE codigo = ? AND id IS NOT ?",
                (p.codigo, p.id)).fetchone()
            if otro:
                raise ErrorTienda("Ya hay otro producto con ese código de barras.")
        with self.con:
            if p.id is None:
                cur = self.con.execute(
                    "INSERT INTO productos (nombre, categoria, presentacion, codigo, costo,"
                    " precio, stock, minimo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (p.nombre, p.categoria, p.presentacion.strip(), p.codigo, p.costo,
                     p.precio, p.stock, p.minimo))
                p.id = cur.lastrowid
                if p.stock:
                    self._movimiento(p.id, "inicial", p.stock, p.stock, usuario_id=usuario_id)
            else:
                anterior = self.producto(p.id)
                if anterior is None:
                    raise ErrorTienda("El producto ya no existe.")
                self.con.execute(
                    "UPDATE productos SET nombre=?, categoria=?, presentacion=?, codigo=?,"
                    " costo=?, precio=?, stock=?, minimo=? WHERE id=?",
                    (p.nombre, p.categoria, p.presentacion.strip(), p.codigo, p.costo,
                     p.precio, p.stock, p.minimo, p.id))
                if p.stock != anterior.stock:
                    self._movimiento(p.id, "ajuste", p.stock - anterior.stock, p.stock,
                                     "Editado desde el formulario", usuario_id)
        return p

    def eliminar_producto(self, producto_id: int) -> None:
        """Lo oculta (no se borra para no dañar el historial de ventas)."""
        with self.con:
            self.con.execute(
                "UPDATE productos SET activo = 0, codigo = NULL WHERE id = ?", (producto_id,))

    def entrada(self, producto_id: int, cantidad: int, costo: int | None = None,
                fijar: bool = False, usuario_id: int | None = None) -> Producto:
        """Llegada de mercancía (suma) o conteo físico (fijar=True deja el stock exacto)."""
        p = self.producto(producto_id)
        if p is None:
            raise ErrorTienda("El producto no existe.")
        if cantidad < 0 or (not fijar and cantidad == 0):
            raise ErrorTienda("Escribe una cantidad válida.")
        nuevo = cantidad if fijar else p.stock + cantidad
        with self.con:
            self.con.execute("UPDATE productos SET stock = ? WHERE id = ?", (nuevo, p.id))
            if costo:
                self.con.execute("UPDATE productos SET costo = ? WHERE id = ?", (costo, p.id))
            self._movimiento(p.id, "ajuste" if fijar else "entrada", nuevo - p.stock, nuevo,
                             "Conteo físico" if fijar else "Llegada de mercancía", usuario_id)
        return self.producto(p.id)

    def valor_inventario(self) -> tuple[int, int, int]:
        """(unidades, valor a costo, valor a precio de venta)."""
        f = self.con.execute(
            "SELECT COALESCE(SUM(stock),0), COALESCE(SUM(stock*costo),0),"
            " COALESCE(SUM(stock*precio),0) FROM productos WHERE activo = 1 AND stock > 0"
        ).fetchone()
        return f[0], f[1], f[2]

    def stock_bajo(self) -> list[Producto]:
        return sorted(self.productos(solo_bajo=True), key=lambda p: p.stock)

    # --------------------------------------------------------------- ventas
    def registrar_venta(self, items: dict[int, int], metodo: str,
                        recibido: int | None = None, usuario_id: int | None = None) -> Venta:
        """items = {producto_id: cantidad}. Descuenta el stock en una sola transacción."""
        items = {pid: c for pid, c in items.items() if c > 0}
        if not items:
            raise ErrorTienda("La venta está vacía.")
        if metodo not in METODOS_PAGO:
            raise ErrorTienda("Método de pago no válido.")
        lineas: list[ItemVenta] = []
        for pid, cant in items.items():
            p = self.producto(pid)
            if p is None:
                raise ErrorTienda("Uno de los productos ya no existe.")
            if cant > p.stock:
                raise StockInsuficiente(f"Solo hay {p.stock} de {p.nombre_completo}.")
            lineas.append(ItemVenta(pid, p.nombre_completo, cant, p.precio, p.costo))
        total = sum(i.subtotal for i in lineas)
        costo_total = sum(i.cantidad * i.costo for i in lineas)
        if metodo == "Efectivo":
            recibido = recibido or total
            if recibido < total:
                raise ErrorTienda(f"Faltan {cop(total - recibido)}.")
        else:
            recibido = None
        momento = self._ahora()
        venta = Venta(fecha=momento.date().isoformat(), hora=momento.strftime("%H:%M"),
                      metodo=metodo, total=total, costo_total=costo_total,
                      items=lineas, recibido=recibido, usuario_id=usuario_id)
        with self.con:
            cur = self.con.execute(
                "INSERT INTO ventas (fecha, hora, metodo, total, costo_total, recibido, usuario_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (venta.fecha, venta.hora, metodo, total, costo_total, recibido, usuario_id))
            venta.id = cur.lastrowid
            for i in lineas:
                self.con.execute(
                    "INSERT INTO venta_items (venta_id, producto_id, nombre, cantidad, precio, costo)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (venta.id, i.producto_id, i.nombre, i.cantidad, i.precio, i.costo))
                self.con.execute(
                    "UPDATE productos SET stock = stock - ? WHERE id = ?", (i.cantidad, i.producto_id))
                stock = self.con.execute(
                    "SELECT stock FROM productos WHERE id = ?", (i.producto_id,)).fetchone()[0]
                self._movimiento(i.producto_id, "venta", -i.cantidad, stock,
                                 f"Venta #{venta.id}", usuario_id)
        return self.venta(venta.id)

    def anular_venta(self, venta_id: int, usuario_id: int | None = None) -> None:
        """Marca la venta como anulada y devuelve los productos al inventario."""
        v = self.venta(venta_id)
        if v is None:
            raise ErrorTienda("La venta no existe.")
        if v.anulada:
            raise ErrorTienda("Esa venta ya estaba anulada.")
        with self.con:
            self.con.execute("UPDATE ventas SET anulada = 1 WHERE id = ?", (venta_id,))
            for i in v.items:
                self.con.execute(
                    "UPDATE productos SET stock = stock + ? WHERE id = ?", (i.cantidad, i.producto_id))
                stock = self.con.execute(
                    "SELECT stock FROM productos WHERE id = ?", (i.producto_id,)).fetchone()[0]
                self._movimiento(i.producto_id, "anulacion", i.cantidad, stock,
                                 f"Anulación venta #{venta_id}", usuario_id)

    _SELECT_VENTA = ("SELECT v.*, COALESCE(u.nombre, '') AS vendedor FROM ventas v"
                     " LEFT JOIN usuarios u ON u.id = v.usuario_id")

    def _venta(self, f: sqlite3.Row) -> Venta:
        items = [ItemVenta(r["producto_id"], r["nombre"], r["cantidad"], r["precio"], r["costo"])
                 for r in self.con.execute(
                     "SELECT * FROM venta_items WHERE venta_id = ? ORDER BY id", (f["id"],))]
        return Venta(id=f["id"], fecha=f["fecha"], hora=f["hora"], metodo=f["metodo"],
                     total=f["total"], costo_total=f["costo_total"], recibido=f["recibido"],
                     anulada=bool(f["anulada"]), usuario_id=f["usuario_id"],
                     vendedor=f["vendedor"], items=items)

    def venta(self, venta_id: int) -> Venta | None:
        f = self.con.execute(self._SELECT_VENTA + " WHERE v.id = ?", (venta_id,)).fetchone()
        return self._venta(f) if f else None

    def ventas_del_dia(self, fecha: str, usuario_id: int | None = None) -> list[Venta]:
        """Ventas de un día. Con usuario_id, solo las de esa persona."""
        sql, params = self._SELECT_VENTA + " WHERE v.fecha = ?", [fecha]
        if usuario_id is not None:
            sql += " AND v.usuario_id = ?"
            params.append(usuario_id)
        filas = self.con.execute(sql + " ORDER BY v.id DESC", params).fetchall()
        return [self._venta(f) for f in filas]

    # ------------------------------------------------------------- reportes
    def resumen(self, desde: str, hasta: str | None = None) -> ResumenDia:
        """Resumen de ventas (no anuladas) entre dos fechas, ambas incluidas."""
        hasta = hasta or desde
        r = ResumenDia(fecha=desde)
        fila = self.con.execute(
            "SELECT COUNT(*), COALESCE(SUM(total),0), COALESCE(SUM(total-costo_total),0)"
            " FROM ventas WHERE anulada = 0 AND fecha BETWEEN ? AND ?", (desde, hasta)).fetchone()
        r.num_ventas, r.total, r.ganancia = fila
        r.por_metodo = {m: t for m, t in self.con.execute(
            "SELECT metodo, SUM(total) FROM ventas WHERE anulada = 0 AND fecha BETWEEN ? AND ?"
            " GROUP BY metodo ORDER BY SUM(total) DESC", (desde, hasta))}
        r.por_vendedor = {n: t for n, t in self.con.execute(
            "SELECT COALESCE(u.nombre, 'Sin usuario'), SUM(v.total) FROM ventas v"
            " LEFT JOIN usuarios u ON u.id = v.usuario_id"
            " WHERE v.anulada = 0 AND v.fecha BETWEEN ? AND ?"
            " GROUP BY v.usuario_id ORDER BY SUM(v.total) DESC", (desde, hasta))}
        r.productos = [ProductoVendido(n, c, t) for n, c, t in self.con.execute(
            "SELECT i.nombre, SUM(i.cantidad), SUM(i.cantidad*i.precio) FROM venta_items i"
            " JOIN ventas v ON v.id = i.venta_id WHERE v.anulada = 0 AND v.fecha BETWEEN ? AND ?"
            " GROUP BY i.nombre ORDER BY SUM(i.cantidad) DESC, SUM(i.cantidad*i.precio) DESC",
            (desde, hasta))]
        return r

    def totales_por_dia(self, desde: str, hasta: str) -> dict[str, int]:
        """{fecha: total} para cada día del rango (con 0 los días sin ventas)."""
        datos = defaultdict(int, {f: t for f, t in self.con.execute(
            "SELECT fecha, SUM(total) FROM ventas WHERE anulada = 0 AND fecha BETWEEN ? AND ?"
            " GROUP BY fecha", (desde, hasta))})
        dias, f = {}, desde
        while f <= hasta:
            dias[f] = datos[f]
            f = sumar_dias(f, 1)
        return dias

    def texto_cierre(self, fecha: str) -> str:
        """Resumen del día listo para pegar en WhatsApp."""
        r = self.resumen(fecha)
        lineas = [f"*STOP 44 — Cierre del {fecha_corta(fecha)}*", "",
                  f"Ventas: {r.num_ventas}", f"*Total: {cop(r.total)}*"]
        lineas += [f"• {m}: {cop(t)}" for m, t in r.por_metodo.items()]
        lineas += ["", f"Ganancia estimada: {cop(r.ganancia)}"]
        if r.productos:
            lineas += ["", "Más vendidos:"]
            lineas += [f"• {p.nombre} ({p.cantidad})" for p in r.productos[:5]]
        bajos = self.stock_bajo()
        if bajos:
            lineas += ["", "⚠️ Por pedir:"]
            lineas += [f"• {p.nombre_completo} (quedan {p.stock})" for p in bajos]
        return "\n".join(lineas)
