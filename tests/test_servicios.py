"""Pruebas de la lógica del negocio. Ejecutar con:  pytest"""

from datetime import datetime

import pytest

from app.modelos import Producto
from app.servicios import ErrorTienda, StockInsuficiente, Tienda
from app.utils import a_centavos, dinero


@pytest.fixture
def tienda():
    t = Tienda(":memory:")
    # dinero en centavos: 1250 = $12,50
    t.guardar_producto(Producto("Aguardiente Norteño", 1250, "Aguardiente", "750 ml",
                                codigo="7861", costo=950, stock=10, minimo=3))
    t.guardar_producto(Producto("Cerveza Pilsener", 125, "Cerveza", "botella 330 ml",
                                costo=90, stock=48, minimo=24))
    return t


def test_formato_dolares():
    assert dinero(1250) == "$12,50"
    assert dinero(123450) == "$1.234,50"
    assert dinero(5) == "$0,05"
    assert dinero(0) == "$0,00"
    assert a_centavos("12,50") == 1250
    assert a_centavos("$12.50") == 1250
    assert a_centavos("12") == 1200
    assert a_centavos("1.234,50") == 123450
    assert a_centavos("") == 0


def test_busqueda_sin_tildes(tienda):
    assert [p.nombre for p in tienda.productos("pilsener")] == ["Cerveza Pilsener"]
    assert tienda.por_codigo("7861").nombre == "Aguardiente Norteño"


def test_venta_descuenta_stock_y_calcula_ganancia(tienda):
    agua, cerv = tienda.productos("aguardiente")[0], tienda.productos("cerveza")[0]
    v = tienda.registrar_venta({agua.id: 2, cerv.id: 6}, "Efectivo", recibido=4000)
    assert v.total == 2 * 1250 + 6 * 125              # $32,50
    assert v.ganancia == 2 * 300 + 6 * 35
    assert v.vueltas == 750                            # paga con $40, vueltas $7,50
    assert tienda.producto(agua.id).stock == 8
    assert tienda.producto(cerv.id).stock == 42


def test_no_vende_mas_de_lo_que_hay(tienda):
    agua = tienda.productos("aguardiente")[0]
    with pytest.raises(StockInsuficiente):
        tienda.registrar_venta({agua.id: 11}, "Deuna")
    assert tienda.producto(agua.id).stock == 10


def test_efectivo_insuficiente(tienda):
    agua = tienda.productos("aguardiente")[0]
    with pytest.raises(ErrorTienda):
        tienda.registrar_venta({agua.id: 1}, "Efectivo", recibido=1000)


def test_anular_devuelve_stock(tienda):
    agua = tienda.productos("aguardiente")[0]
    v = tienda.registrar_venta({agua.id: 3}, "Deuna")
    tienda.anular_venta(v.id)
    assert tienda.producto(agua.id).stock == 10
    assert tienda.resumen(v.fecha).total == 0
    with pytest.raises(ErrorTienda):
        tienda.anular_venta(v.id)


def test_entrada_y_conteo(tienda):
    agua = tienda.productos("aguardiente")[0]
    assert tienda.entrada(agua.id, 12, costo=1000).stock == 22
    assert tienda.producto(agua.id).costo == 1000
    assert tienda.entrada(agua.id, 20, fijar=True).stock == 20


def test_resumen_y_cierre(tienda):
    agua, cerv = tienda.productos("aguardiente")[0], tienda.productos("cerveza")[0]
    tienda.registrar_venta({agua.id: 1}, "Efectivo")
    tienda.registrar_venta({cerv.id: 30}, "Deuna")
    hoy = datetime.now().date().isoformat()
    r = tienda.resumen(hoy)
    assert r.num_ventas == 2 and r.total == 1250 + 3750
    assert r.por_metodo == {"Deuna": 3750, "Efectivo": 1250}
    assert r.productos[0].nombre.startswith("Cerveza")
    texto = tienda.texto_cierre(hoy)
    assert "$50,00" in texto and "Por pedir" in texto  # quedan 18 cervezas < 24


def test_codigo_repetido_y_validaciones(tienda):
    with pytest.raises(ErrorTienda):
        tienda.guardar_producto(Producto("Otro", 1000, codigo="7861"))
    with pytest.raises(ErrorTienda):
        tienda.guardar_producto(Producto("Sin precio", 0))


def test_eliminar_no_rompe_historial(tienda):
    agua = tienda.productos("aguardiente")[0]
    v = tienda.registrar_venta({agua.id: 1}, "Efectivo")
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
    v = tienda.registrar_venta({agua.id: 1}, "Deuna", usuario_id=laura)
    tienda.registrar_venta({cerv.id: 2}, "Deuna")
    assert v.vendedor == "Laura"
    assert len(tienda.ventas_del_dia(v.fecha, usuario_id=laura)) == 1
    assert tienda.resumen(v.fecha).por_vendedor == {"Laura": 1250, "Sin usuario": 250}


def test_kardex_registra_movimientos(tienda):
    agua = tienda.productos("aguardiente")[0]
    tienda.entrada(agua.id, 5)
    v = tienda.registrar_venta({agua.id: 2}, "Efectivo")
    tienda.anular_venta(v.id)
    tipos = [r["tipo"] for r in tienda.con.execute(
        "SELECT tipo FROM movimientos WHERE producto_id = ? ORDER BY id", (agua.id,))]
    assert tipos == ["inicial", "entrada", "venta", "anulacion"]
