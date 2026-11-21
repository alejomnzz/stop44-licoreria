"""Pruebas de la lógica del negocio. Ejecutar con:  pytest"""

from datetime import datetime

import pytest

from app.modelos import Producto
from app.servicios import ErrorTienda, StockInsuficiente, Tienda
from app.utils import a_entero, cop


@pytest.fixture
def tienda():
    t = Tienda(":memory:")
    t.guardar_producto(Producto("Aguardiente Antioqueño", 45000, "Aguardiente", "750 ml",
                                codigo="7702", costo=36000, stock=10, minimo=3))
    t.guardar_producto(Producto("Cerveza Águila", 3500, "Cerveza", "lata 330 ml",
                                costo=2500, stock=48, minimo=24))
    return t


def test_formato_pesos():
    assert cop(1234567) == "$1.234.567"
    assert cop(0) == "$0"
    assert a_entero("$12.500") == 12500


def test_busqueda_sin_tildes(tienda):
    assert [p.nombre for p in tienda.productos("aguila")] == ["Cerveza Águila"]
    assert tienda.por_codigo("7702").nombre == "Aguardiente Antioqueño"


def test_venta_descuenta_stock_y_calcula_ganancia(tienda):
    agua, cerv = tienda.productos("aguardiente")[0], tienda.productos("cerveza")[0]
    v = tienda.registrar_venta({agua.id: 2, cerv.id: 6}, "Efectivo", recibido=120000)
    assert v.total == 2 * 45000 + 6 * 3500
    assert v.ganancia == 2 * 9000 + 6 * 1000
    assert v.vueltas == 120000 - v.total
    assert tienda.producto(agua.id).stock == 8
    assert tienda.producto(cerv.id).stock == 42


def test_no_vende_mas_de_lo_que_hay(tienda):
    agua = tienda.productos("aguardiente")[0]
    with pytest.raises(StockInsuficiente):
        tienda.registrar_venta({agua.id: 11}, "Nequi")
    assert tienda.producto(agua.id).stock == 10


def test_efectivo_insuficiente(tienda):
    agua = tienda.productos("aguardiente")[0]
    with pytest.raises(ErrorTienda):
        tienda.registrar_venta({agua.id: 1}, "Efectivo", recibido=20000)


def test_anular_devuelve_stock(tienda):
    agua = tienda.productos("aguardiente")[0]
    v = tienda.registrar_venta({agua.id: 3}, "Nequi")
    tienda.anular_venta(v.id)
    assert tienda.producto(agua.id).stock == 10
    assert tienda.resumen(v.fecha).total == 0
    with pytest.raises(ErrorTienda):
        tienda.anular_venta(v.id)


def test_entrada_y_conteo(tienda):
    agua = tienda.productos("aguardiente")[0]
    assert tienda.entrada(agua.id, 12, costo=37000).stock == 22
    assert tienda.producto(agua.id).costo == 37000
    assert tienda.entrada(agua.id, 20, fijar=True).stock == 20


def test_resumen_y_cierre(tienda):
    agua, cerv = tienda.productos("aguardiente")[0], tienda.productos("cerveza")[0]
    tienda.registrar_venta({agua.id: 1}, "Efectivo")
    tienda.registrar_venta({cerv.id: 30}, "Nequi")
    hoy = datetime.now().date().isoformat()
    r = tienda.resumen(hoy)
    assert r.num_ventas == 2 and r.total == 45000 + 105000
    assert r.por_metodo == {"Nequi": 105000, "Efectivo": 45000}
    assert r.productos[0].nombre.startswith("Cerveza")
    texto = tienda.texto_cierre(hoy)
    assert "$150.000" in texto and "Por pedir" in texto  # quedan 18 cervezas < 24


def test_codigo_repetido_y_validaciones(tienda):
    with pytest.raises(ErrorTienda):
        tienda.guardar_producto(Producto("Otro", 1000, codigo="7702"))
    with pytest.raises(ErrorTienda):
        tienda.guardar_producto(Producto("Sin precio", 0))


def test_eliminar_no_rompe_historial(tienda):
    agua = tienda.productos("aguardiente")[0]
    v = tienda.registrar_venta({agua.id: 1}, "Tarjeta")
    tienda.eliminar_producto(agua.id)
    assert tienda.producto(agua.id) is None
    assert tienda.venta(v.id).items[0].nombre.startswith("Aguardiente")


def test_metodo_de_pago_invalido(tienda):
    agua = tienda.productos("aguardiente")[0]
    with pytest.raises(ErrorTienda):
        tienda.registrar_venta({agua.id: 1}, "Bitcoin")


def test_ventas_por_vendedor(tienda):
    con = tienda.con
    con.execute("INSERT INTO usuarios (nombre, usuario, clave_hash, rol, estado)"
                " VALUES ('Laura', 'laura', 'x', 'vendedor', 'activo')")
    laura = con.execute("SELECT id FROM usuarios WHERE usuario = 'laura'").fetchone()[0]
    agua, cerv = tienda.productos("aguardiente")[0], tienda.productos("cerveza")[0]
    v = tienda.registrar_venta({agua.id: 1}, "Nequi", usuario_id=laura)
    tienda.registrar_venta({cerv.id: 2}, "Nequi")
    assert v.vendedor == "Laura"
    assert len(tienda.ventas_del_dia(v.fecha, usuario_id=laura)) == 1
    assert tienda.resumen(v.fecha).por_vendedor == {"Laura": 45000, "Sin usuario": 7000}


def test_kardex_registra_movimientos(tienda):
    agua = tienda.productos("aguardiente")[0]
    tienda.entrada(agua.id, 5)
    v = tienda.registrar_venta({agua.id: 2}, "Tarjeta")
    tienda.anular_venta(v.id)
    tipos = [r["tipo"] for r in tienda.con.execute(
        "SELECT tipo FROM movimientos WHERE producto_id = ? ORDER BY id", (agua.id,))]
    assert tipos == ["inicial", "entrada", "venta", "anulacion"]
