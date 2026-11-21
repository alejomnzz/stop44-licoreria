"""Pruebas de la API: se hacen peticiones como si fuera el navegador. Ejecutar con:  pytest"""

import os
import tempfile
from pathlib import Path

import pytest

# Base de datos temporal: las pruebas nunca tocan datos/stop44.db
_tmp = tempfile.mkdtemp()
os.environ["STOP44_DB"] = str(Path(_tmp) / "prueba.db")
os.environ["STOP44_SECRET"] = "clave-solo-para-pruebas-de-la-api-0123456789"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, tienda  # noqa: E402


@pytest.fixture
def cliente():
    for tabla in ("movimientos", "fotos", "venta_items", "abonos", "ventas", "clientes", "productos", "usuarios"):
        tienda.con.execute(f"DELETE FROM {tabla}")
    tienda.con.commit()
    return TestClient(app)


def crear_admin(c):
    r = c.post("/api/auth/registro", json={"nombre": "Dueña", "usuario": "duena", "clave": "secreta123"})
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "admin"


def crear_producto(c, **extra):
    datos = {"nombre": "Aguardiente Norteño", "precio": 1250, "costo": 1000,    # centavos
             "stock": 10, "categoria": "Aguardiente", "presentacion": "750 ml"} | extra
    r = c.post("/api/productos", json=datos)
    assert r.status_code == 201, r.text
    return r.json()


def test_sin_sesion_no_deja_entrar(cliente):
    assert cliente.get("/api/auth/estado").json() == {"hay_usuarios": False}
    assert cliente.get("/api/productos").status_code == 401


def test_flujo_completo_admin(cliente):
    crear_admin(cliente)                                  # queda con sesión abierta
    assert cliente.get("/api/auth/yo").json()["nombre"] == "Dueña"
    p = crear_producto(cliente, codigo="7861")
    assert p["margen"] == 20

    r = cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 2}],
                                          "metodo": "Efectivo", "recibido": 3000})
    assert r.status_code == 201
    venta = r.json()
    assert venta["total"] == 2500 and venta["vueltas"] == 500 and venta["vendedor"] == "Dueña"

    assert cliente.get("/api/productos/codigo/7861").json()["stock"] == 8
    assert cliente.get("/api/resumen").json()["total"] == 2500
    assert "$25,00" in cliente.get("/api/cierre").json()["texto"]

    cliente.post(f"/api/ventas/{venta['id']}/anular")
    assert cliente.get("/api/productos/codigo/7861").json()["stock"] == 10


def test_errores_de_negocio_llegan_claros(cliente):
    crear_admin(cliente)
    p = crear_producto(cliente)
    r = cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 50}],
                                          "metodo": "Deuna"})
    assert r.status_code == 400 and "Solo hay 10" in r.json()["detail"]


def test_vendedor_tiene_permisos_limitados(cliente):
    crear_admin(cliente)
    p = crear_producto(cliente)
    vendedor = TestClient(app)                            # otro navegador
    r = vendedor.post("/api/auth/registro", json={"nombre": "Laura", "usuario": "laura", "clave": "clave456"})
    laura = r.json()["usuario"]
    assert laura["estado"] == "pendiente"
    assert vendedor.post("/api/auth/ingresar", json={"usuario": "laura", "clave": "clave456"}).status_code == 400

    cliente.patch(f"/api/usuarios/{laura['id']}", json={"estado": "activo"})   # la dueña la aprueba
    assert vendedor.post("/api/auth/ingresar", json={"usuario": "laura", "clave": "clave456"}).status_code == 200

    productos = vendedor.get("/api/productos").json()
    assert "costo" not in productos[0]                    # el vendedor no ve costos
    r = vendedor.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 1}],
                                           "metodo": "Deuna"})
    assert r.status_code == 201 and "ganancia" not in r.json()
    assert vendedor.post("/api/productos", json={"nombre": "X", "precio": 1000}).status_code == 403
    assert vendedor.get("/api/resumen").status_code == 403
    assert vendedor.post(f"/api/ventas/{r.json()['id']}/anular").status_code == 403


def test_salir_cierra_la_sesion(cliente):
    crear_admin(cliente)
    cliente.post("/api/auth/salir")
    assert cliente.get("/api/auth/yo").status_code == 401


# PNG de 1x1 píxel, para probar las fotos
PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def test_fotos_de_productos(cliente):
    crear_admin(cliente)
    p = crear_producto(cliente)
    assert p["foto"] is None
    r = cliente.put(f"/api/productos/{p['id']}/foto", json={"imagen": "data:image/png;base64," + PNG})
    assert r.status_code == 200 and r.json()["foto"]
    r = cliente.get(f"/api/productos/{p['id']}/foto")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"

    # editar el producto no borra la foto
    r = cliente.put(f"/api/productos/{p['id']}", json={"nombre": "Otro nombre", "precio": 1300})
    assert r.json()["foto"]

    # un archivo que no es imagen se rechaza
    r = cliente.put(f"/api/productos/{p['id']}/foto", json={"imagen": "aG9sYSBtdW5kbw=="})
    assert r.status_code == 400 and "no es una foto" in r.json()["detail"]

    cliente.delete(f"/api/productos/{p['id']}/foto")
    assert cliente.get(f"/api/productos/{p['id']}/foto").status_code == 404


def test_historial_de_stock(cliente):
    crear_admin(cliente)
    p = crear_producto(cliente)
    cliente.post(f"/api/productos/{p['id']}/entrada", json={"cantidad": 6})
    cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 2}], "metodo": "Deuna"})
    historial = cliente.get(f"/api/productos/{p['id']}/movimientos").json()
    assert [m["tipo"] for m in historial] == ["venta", "entrada", "inicial"]
    assert historial[0]["stock_final"] == 14 and historial[0]["usuario"] == "Dueña"


def test_muchos_pedidos_al_mismo_tiempo(cliente):
    """La app pide varias cosas a la vez (por ejemplo el Resumen); ninguna debe fallar."""
    from concurrent.futures import ThreadPoolExecutor
    crear_admin(cliente)
    p = crear_producto(cliente)
    cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 1}], "metodo": "Deuna"})
    rutas = ["/api/productos", "/api/resumen", "/api/ventas", "/api/stock-bajo", "/api/inventario/valor",
             "/api/auth/yo", "/api/usuarios", "/api/hoy"] * 6
    with ThreadPoolExecutor(max_workers=12) as hilos:
        estados = list(hilos.map(lambda r: cliente.get(r).status_code, rutas))
    assert estados == [200] * len(rutas)


def test_salud_y_respaldo(cliente):
    assert cliente.get("/api/salud").json() == {"ok": True}
    assert cliente.get("/api/respaldo").status_code == 401           # sin sesión no
    crear_admin(cliente)
    crear_producto(cliente)
    r = cliente.get("/api/respaldo")
    assert r.status_code == 200 and r.content.startswith(b"SQLite format 3")
    import sqlite3, tempfile, pathlib
    ruta = pathlib.Path(tempfile.mkdtemp()) / "copia.db"
    ruta.write_bytes(r.content)
    assert sqlite3.connect(ruta).execute("SELECT nombre FROM productos").fetchone()[0] == "Aguardiente Norteño"


def test_reporte_excel(cliente):
    import io
    import openpyxl
    assert cliente.get("/api/reporte").status_code == 401
    crear_admin(cliente)
    p = crear_producto(cliente)
    cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 2}], "metodo": "Efectivo"})
    cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 1}], "metodo": "Deuna"})
    v = cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 3}], "metodo": "Deuna"}).json()
    cliente.post(f"/api/ventas/{v['id']}/anular")
    r = cliente.get("/api/reporte")
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    libro = openpyxl.load_workbook(io.BytesIO(r.content), data_only=True)   # valores ya calculados
    assert libro.sheetnames == ["Resumen", "Por día", "Por semana", "Por mes", "Productos", "Fiados",
                                "Ventas", "Abonos", "Detalle", "Inventario"]
    hoy = libro["Resumen"]
    assert hoy["A9"].value == "Hoy" and hoy["B9"].value == 2            # la anulada no cuenta
    assert hoy["C9"].value == 37.5                                      # 3 × $12,50
    dia = libro["Por día"]
    assert (dia["D2"].value, dia["E2"].value, dia["F2"].value, dia["G2"].value) == (25.0, 12.5, 0, 37.5)
    assert libro["Ventas"].max_row == 4 and libro["Ventas"]["N4"].value == "Anulada"


def test_fiados_por_la_api(cliente):
    crear_admin(cliente)
    p = crear_producto(cliente)
    juan = cliente.post("/api/clientes", json={"nombre": "Juan", "telefono": "0991234567"}).json()
    r = cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 2}],
                                          "metodo": "Fiado", "cliente_id": juan["id"]})
    assert r.status_code == 201 and r.json()["cliente"] == "Juan"
    assert cliente.get("/api/clientes").json()["por_cobrar"] == 2500
    r = cliente.post(f"/api/clientes/{juan['id']}/abonos", json={"monto": 1000, "metodo": "Deuna"})
    assert r.json()["saldo"] == 1500
    cuenta = cliente.get(f"/api/clientes/{juan['id']}").json()["cuenta"]
    assert [m["tipo"] for m in cuenta] == ["abono", "fiado"]
    assert cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 1}],
                                             "metodo": "Fiado"}).status_code == 400   # sin cliente
    resumen = cliente.get("/api/resumen").json()
    assert resumen["abonos"] == {"Deuna": 1000} and resumen["por_cobrar"] == 1500


def test_reporte_excel_con_fiados(cliente):
    import io
    import openpyxl
    crear_admin(cliente)
    p = crear_producto(cliente)
    juan = cliente.post("/api/clientes", json={"nombre": "Juan"}).json()
    cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 2}], "metodo": "Fiado", "cliente_id": juan["id"]})
    cliente.post(f"/api/clientes/{juan['id']}/abonos", json={"monto": 1000, "metodo": "Efectivo"})
    libro = openpyxl.load_workbook(io.BytesIO(cliente.get("/api/reporte").content), data_only=True)
    dia = libro["Por día"]
    assert (dia["F2"].value, dia["G2"].value, dia["J2"].value) == (25.0, 25.0, 10.0)   # fiado, total, abonos
    fiados = libro["Fiados"]
    assert [fiados["A2"].value, fiados["C2"].value, fiados["D2"].value, fiados["E2"].value] == ["Juan", 25.0, 10.0, 15.0]
    assert libro["Resumen"]["C14"].value == 15.0
