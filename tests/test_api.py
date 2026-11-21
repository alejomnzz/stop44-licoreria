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
    for tabla in ("movimientos", "venta_items", "ventas", "productos", "usuarios"):
        tienda.con.execute(f"DELETE FROM {tabla}")
    tienda.con.commit()
    return TestClient(app)


def crear_admin(c):
    r = c.post("/api/auth/registro", json={"nombre": "Dueña", "usuario": "duena", "clave": "secreta123"})
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "admin"


def crear_producto(c, **extra):
    datos = {"nombre": "Aguardiente Antioqueño", "precio": 45000, "costo": 36000,
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
    p = crear_producto(cliente, codigo="7702")
    assert p["margen"] == 20

    r = cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 2}],
                                          "metodo": "Efectivo", "recibido": 100000})
    assert r.status_code == 201
    venta = r.json()
    assert venta["total"] == 90000 and venta["vueltas"] == 10000 and venta["vendedor"] == "Dueña"

    assert cliente.get("/api/productos/codigo/7702").json()["stock"] == 8
    assert cliente.get("/api/resumen").json()["total"] == 90000
    assert "$90.000" in cliente.get("/api/cierre").json()["texto"]

    cliente.post(f"/api/ventas/{venta['id']}/anular")
    assert cliente.get("/api/productos/codigo/7702").json()["stock"] == 10


def test_errores_de_negocio_llegan_claros(cliente):
    crear_admin(cliente)
    p = crear_producto(cliente)
    r = cliente.post("/api/ventas", json={"items": [{"producto_id": p["id"], "cantidad": 50}],
                                          "metodo": "Nequi"})
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
                                           "metodo": "Nequi"})
    assert r.status_code == 201 and "ganancia" not in r.json()
    assert vendedor.post("/api/productos", json={"nombre": "X", "precio": 1000}).status_code == 403
    assert vendedor.get("/api/resumen").status_code == 403
    assert vendedor.post(f"/api/ventas/{r.json()['id']}/anular").status_code == 403


def test_salir_cierra_la_sesion(cliente):
    crear_admin(cliente)
    cliente.post("/api/auth/salir")
    assert cliente.get("/api/auth/yo").status_code == 401
