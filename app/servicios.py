"""Lógica del negocio: inventario, ventas y reportes.

La API (FastAPI) solo llama a estos métodos. Aquí no hay nada de web,
así que todo se puede probar con pytest.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import db
from .modelos import METODOS_ABONO, METODOS_PAGO, Cliente, ItemVenta, Producto, ProductoVendido, ResumenDia, Venta
from .utils import ahora, dinero, fecha_corta, normalizar, sumar_dias


class ErrorTienda(Exception):
    """Error de negocio con un mensaje listo para mostrar al usuario."""


class StockInsuficiente(ErrorTienda):
    pass


FOTO_MAX_BYTES = 600 * 1024            # la app las achica antes, esto es solo un tope
_FIRMAS_IMAGEN = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}


def tipo_de_imagen(datos: bytes) -> str | None:
    """Reconoce la imagen por sus primeros bytes (no confía en el nombre del archivo)."""
    for firma, tipo in _FIRMAS_IMAGEN.items():
        if datos.startswith(firma):
            return tipo
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


class Tienda:
    def __init__(self, ruta: str | Path | None = None):
        self.bd = db.BaseDeDatos(ruta)

    @property
    def con(self) -> sqlite3.Connection:
        return self.bd.con          # la conexión de este hilo

    # ------------------------------------------------------------------ util
    def _ahora(self) -> datetime:
        return ahora()          # hora de Ecuador

    @staticmethod
    def _producto(fila: sqlite3.Row) -> Producto:
        return Producto(
            id=fila["id"], nombre=fila["nombre"], categoria=fila["categoria"],
            presentacion=fila["presentacion"], codigo=fila["codigo"],
            costo=fila["costo"], precio=fila["precio"], stock=fila["stock"],
            minimo=fila["minimo"], foto=fila["foto"],
        )

    _SELECT_PRODUCTO = ("SELECT p.*, f.version AS foto FROM productos p"
                        " LEFT JOIN fotos f ON f.producto_id = p.id WHERE p.activo = 1")

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
        filas = self.con.execute(self._SELECT_PRODUCTO).fetchall()
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
            self._SELECT_PRODUCTO + " AND p.id = ?", (producto_id,)).fetchone()
        return self._producto(f) if f else None

    def por_codigo(self, codigo: str) -> Producto | None:
        f = self.con.execute(
            self._SELECT_PRODUCTO + " AND p.codigo = ?", (codigo.strip(),)).fetchone()
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
                "SELECT nombre, presentacion FROM productos WHERE codigo = ? AND id IS NOT ?",
                (p.codigo, p.id)).fetchone()
            if otro:
                nombre = f"{otro['nombre']} {otro['presentacion'] or ''}".strip()
                raise ErrorTienda(f"Ese código de barras ya es de {nombre}.")
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
        return self.producto(p.id)

    def eliminar_producto(self, producto_id: int) -> None:
        """Lo oculta (no se borra para no dañar el historial de ventas)."""
        with self.con:
            self.con.execute(
                "UPDATE productos SET activo = 0, codigo = NULL WHERE id = ?", (producto_id,))
            self.con.execute("DELETE FROM fotos WHERE producto_id = ?", (producto_id,))

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

    # ---------------------------------------------------------------- fotos
    def guardar_foto(self, producto_id: int, datos: bytes) -> str:
        """Guarda (o reemplaza) la foto del producto. Devuelve la versión nueva."""
        if self.producto(producto_id) is None:
            raise ErrorTienda("El producto no existe.")
        if len(datos) > FOTO_MAX_BYTES:
            raise ErrorTienda("La foto es muy pesada. Prueba con otra.")
        tipo = tipo_de_imagen(datos)
        if tipo is None:
            raise ErrorTienda("Ese archivo no es una foto (usa JPG, PNG o WEBP).")
        version = secrets.token_hex(4)
        with self.con:
            self.con.execute(
                "INSERT INTO fotos (producto_id, imagen, tipo, version) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(producto_id) DO UPDATE SET imagen = excluded.imagen,"
                " tipo = excluded.tipo, version = excluded.version",
                (producto_id, datos, tipo, version))
        return version

    def foto(self, producto_id: int) -> tuple[bytes, str] | None:
        f = self.con.execute(
            "SELECT imagen, tipo FROM fotos WHERE producto_id = ?", (producto_id,)).fetchone()
        return (f["imagen"], f["tipo"]) if f else None

    def quitar_foto(self, producto_id: int) -> None:
        with self.con:
            self.con.execute("DELETE FROM fotos WHERE producto_id = ?", (producto_id,))

    def movimientos(self, producto_id: int, limite: int = 50) -> list[dict]:
        """Historial de cambios de stock de un producto (kardex), del más nuevo al más viejo."""
        filas = self.con.execute(
            "SELECT m.fecha, m.tipo, m.cantidad, m.stock_final, m.nota, COALESCE(u.nombre, '') AS usuario"
            " FROM movimientos m LEFT JOIN usuarios u ON u.id = m.usuario_id"
            " WHERE m.producto_id = ? ORDER BY m.id DESC LIMIT ?", (producto_id, limite))
        return [dict(f) for f in filas]

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
    def registrar_venta(self, items: dict[int, int], metodo: str, recibido: int | None = None,
                        usuario_id: int | None = None, cliente_id: int | None = None) -> Venta:
        """items = {producto_id: cantidad}. Descuenta el stock en una sola transacción.

        Con metodo="Fiado" hay que indicar el cliente: la venta queda a su cuenta.
        """
        items = {pid: c for pid, c in items.items() if c > 0}
        if not items:
            raise ErrorTienda("La venta está vacía.")
        if metodo not in METODOS_PAGO:
            raise ErrorTienda("Método de pago no válido.")
        if metodo == "Fiado":
            if not cliente_id or self.cliente(cliente_id) is None:
                raise ErrorTienda("Elige a qué cliente se le fía.")
        else:
            cliente_id = None
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
                raise ErrorTienda(f"Faltan {dinero(total - recibido)}.")
        else:
            recibido = None
        momento = self._ahora()
        venta = Venta(fecha=momento.date().isoformat(), hora=momento.strftime("%H:%M"),
                      metodo=metodo, total=total, costo_total=costo_total,
                      items=lineas, recibido=recibido, usuario_id=usuario_id, cliente_id=cliente_id)
        with self.con:
            cur = self.con.execute(
                "INSERT INTO ventas (fecha, hora, metodo, total, costo_total, recibido, usuario_id, cliente_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (venta.fecha, venta.hora, metodo, total, costo_total, recibido, usuario_id, cliente_id))
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

    _SELECT_VENTA = ("SELECT v.*, COALESCE(u.nombre, '') AS vendedor, COALESCE(c.nombre, '') AS cliente"
                     " FROM ventas v LEFT JOIN usuarios u ON u.id = v.usuario_id"
                     " LEFT JOIN clientes c ON c.id = v.cliente_id")

    def _venta(self, f: sqlite3.Row) -> Venta:
        items = [ItemVenta(r["producto_id"], r["nombre"], r["cantidad"], r["precio"], r["costo"])
                 for r in self.con.execute(
                     "SELECT * FROM venta_items WHERE venta_id = ? ORDER BY id", (f["id"],))]
        return Venta(id=f["id"], fecha=f["fecha"], hora=f["hora"], metodo=f["metodo"],
                     total=f["total"], costo_total=f["costo_total"], recibido=f["recibido"],
                     anulada=bool(f["anulada"]), usuario_id=f["usuario_id"],
                     vendedor=f["vendedor"], cliente_id=f["cliente_id"], cliente=f["cliente"], items=items)

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
        r.abonos = {m: t for m, t in self.con.execute(
            "SELECT metodo, SUM(monto) FROM abonos WHERE anulado = 0 AND fecha BETWEEN ? AND ?"
            " GROUP BY metodo", (desde, hasta))}
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

    def ventas_por_hora(self, desde: str, hasta: str) -> dict[int, int]:
        """{hora: total} de 0 a 23, para saber a qué horas se vende más."""
        datos = {h: t for h, t in self.con.execute(
            "SELECT CAST(substr(hora, 1, 2) AS INTEGER), SUM(total) FROM ventas"
            " WHERE anulada = 0 AND fecha BETWEEN ? AND ? GROUP BY 1", (desde, hasta))}
        return {h: datos.get(h, 0) for h in range(24)}

    def respaldo(self) -> bytes:
        """Copia completa de la base de datos (ventas, productos, fotos, usuarios) en un archivo."""
        import tempfile
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "copia.db"
            destino = sqlite3.connect(ruta)
            self.con.backup(destino)        # copia segura aunque la app esté en uso
            destino.close()
            return ruta.read_bytes()

    # --------------------------------------------------------------- fiados
    _SELECT_CLIENTE = """
        SELECT c.*,
          COALESCE((SELECT SUM(total) FROM ventas
                    WHERE cliente_id = c.id AND metodo = 'Fiado' AND anulada = 0), 0) AS fiado,
          COALESCE((SELECT SUM(monto) FROM abonos WHERE cliente_id = c.id AND anulado = 0), 0) AS abonado,
          COALESCE((SELECT MAX(m) FROM (
              SELECT fecha || ' ' || hora AS m FROM ventas WHERE cliente_id = c.id AND anulada = 0
              UNION ALL
              SELECT fecha || ' ' || hora FROM abonos WHERE cliente_id = c.id AND anulado = 0)), '') AS ultimo
        FROM clientes c WHERE c.activo = 1"""

    @staticmethod
    def _cliente(f: sqlite3.Row) -> Cliente:
        return Cliente(id=f["id"], nombre=f["nombre"], telefono=f["telefono"], nota=f["nota"],
                       creado=f["creado"], fiado=f["fiado"], abonado=f["abonado"], ultimo_movimiento=f["ultimo"])

    def clientes(self, buscar: str = "") -> list[Cliente]:
        """Clientes de fiado, primero los que más deben."""
        lista = [self._cliente(f) for f in self.con.execute(self._SELECT_CLIENTE)]
        q = normalizar(buscar.strip())
        if q:
            lista = [c for c in lista if q in normalizar(f"{c.nombre} {c.telefono}")]
        return sorted(lista, key=lambda c: (-c.saldo, normalizar(c.nombre)))

    def cliente(self, cliente_id: int) -> Cliente | None:
        f = self.con.execute(self._SELECT_CLIENTE + " AND c.id = ?", (cliente_id,)).fetchone()
        return self._cliente(f) if f else None

    def guardar_cliente(self, c: Cliente) -> Cliente:
        c.nombre = " ".join(c.nombre.split())
        c.telefono = re.sub(r"[^\d+]", "", c.telefono or "")
        if len(c.nombre) < 2:
            raise ErrorTienda("Escribe el nombre del cliente.")
        repetido = next((x for x in self.clientes()
                         if normalizar(x.nombre) == normalizar(c.nombre) and x.id != c.id), None)
        if repetido:
            raise ErrorTienda(f"Ya hay un cliente llamado {repetido.nombre}. Agrégale el apellido o un apodo.")
        with self.con:
            if c.id is None:
                cur = self.con.execute(
                    "INSERT INTO clientes (nombre, telefono, nota, creado) VALUES (?, ?, ?, ?)",
                    (c.nombre, c.telefono, c.nota.strip(), self._ahora().strftime("%Y-%m-%d %H:%M:%S")))
                c.id = cur.lastrowid
            else:
                if self.cliente(c.id) is None:
                    raise ErrorTienda("Ese cliente ya no existe.")
                self.con.execute("UPDATE clientes SET nombre = ?, telefono = ?, nota = ? WHERE id = ?",
                                 (c.nombre, c.telefono, c.nota.strip(), c.id))
        return self.cliente(c.id)

    def eliminar_cliente(self, cliente_id: int) -> None:
        c = self.cliente(cliente_id)
        if c is None:
            raise ErrorTienda("Ese cliente ya no existe.")
        if c.saldo > 0:
            raise ErrorTienda(f"{c.nombre} todavía debe {dinero(c.saldo)}. Solo se puede quitar cuando no deba nada.")
        with self.con:
            self.con.execute("UPDATE clientes SET activo = 0 WHERE id = ?", (cliente_id,))

    def registrar_abono(self, cliente_id: int, monto: int, metodo: str,
                        usuario_id: int | None = None) -> Cliente:
        c = self.cliente(cliente_id)
        if c is None:
            raise ErrorTienda("Ese cliente ya no existe.")
        if metodo not in METODOS_ABONO:
            raise ErrorTienda("El abono se recibe en efectivo o por Deuna.")
        if monto <= 0:
            raise ErrorTienda("Escribe cuánto está pagando.")
        if monto > c.saldo:
            raise ErrorTienda(f"{c.nombre} solo debe {dinero(c.saldo)}.")
        momento = self._ahora()
        with self.con:
            self.con.execute(
                "INSERT INTO abonos (cliente_id, fecha, hora, monto, metodo, usuario_id) VALUES (?, ?, ?, ?, ?, ?)",
                (cliente_id, momento.date().isoformat(), momento.strftime("%H:%M"), monto, metodo, usuario_id))
        return self.cliente(cliente_id)

    def anular_abono(self, abono_id: int) -> Cliente:
        f = self.con.execute("SELECT cliente_id, anulado FROM abonos WHERE id = ?", (abono_id,)).fetchone()
        if f is None:
            raise ErrorTienda("Ese abono no existe.")
        if f["anulado"]:
            raise ErrorTienda("Ese abono ya estaba anulado.")
        with self.con:
            self.con.execute("UPDATE abonos SET anulado = 1 WHERE id = ?", (abono_id,))
        return self.cliente(f["cliente_id"])

    def cuenta_cliente(self, cliente_id: int) -> list[dict]:
        """Lo que el cliente llevó fiado y lo que ha abonado, del más nuevo al más viejo."""
        movs = [{"tipo": "fiado", "id": v.id, "fecha": v.fecha, "hora": v.hora, "monto": v.total,
                 "detalle": ", ".join(f"{i.cantidad}× {i.nombre}" for i in v.items),
                 "usuario": v.vendedor, "anulado": v.anulada}
                for v in (self._venta(f) for f in self.con.execute(
                    self._SELECT_VENTA + " WHERE v.cliente_id = ? AND v.metodo = 'Fiado'", (cliente_id,)))]
        movs += [{"tipo": "abono", "id": f["id"], "fecha": f["fecha"], "hora": f["hora"], "monto": f["monto"],
                  "detalle": f"Abono en {f['metodo'].lower()}" if f["metodo"] == "Efectivo" else "Abono por Deuna",
                  "usuario": f["usuario"], "anulado": bool(f["anulado"])}
                 for f in self.con.execute(
                     "SELECT a.*, COALESCE(u.nombre, '') AS usuario FROM abonos a"
                     " LEFT JOIN usuarios u ON u.id = a.usuario_id WHERE a.cliente_id = ?", (cliente_id,))]
        return sorted(movs, key=lambda m: (m["fecha"], m["hora"], m["tipo"] == "abono", m["id"]), reverse=True)

    def total_por_cobrar(self) -> int:
        return sum(c.saldo for c in self.clientes())

    def texto_cierre(self, fecha: str) -> str:
        """Resumen del día listo para pegar en WhatsApp."""
        r = self.resumen(fecha)
        lineas = [f"*STOP 44 — Cierre del {fecha_corta(fecha)}*", "",
                  f"Ventas: {r.num_ventas}", f"*Total: {dinero(r.total)}*"]
        lineas += [f"• {m}: {dinero(t)}" for m, t in r.por_metodo.items()]
        if r.abonos:
            lineas += ["", f"Abonos de fiados: {dinero(sum(r.abonos.values()))}"]
            lineas += [f"• {m}: {dinero(t)}" for m, t in r.abonos.items()]
        en_caja = r.por_metodo.get("Efectivo", 0) + r.abonos.get("Efectivo", 0)
        lineas += ["", f"*Efectivo en caja: {dinero(en_caja)}*"]
        lineas += ["", f"Ganancia estimada: {dinero(r.ganancia)}"]
        por_cobrar = self.total_por_cobrar()
        if por_cobrar:
            lineas += [f"Fiados por cobrar (total): {dinero(por_cobrar)}"]
        if r.productos:
            lineas += ["", "Más vendidos:"]
            lineas += [f"• {p.nombre} ({p.cantidad})" for p in r.productos[:5]]
        bajos = self.stock_bajo()
        if bajos:
            lineas += ["", "⚠️ Por pedir:"]
            lineas += [f"• {p.nombre_completo} (quedan {p.stock})" for p in bajos]
        return "\n".join(lineas)
