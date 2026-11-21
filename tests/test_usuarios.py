"""Pruebas de cuentas de usuario. Ejecutar con:  pytest"""

import pytest

from app.db import conectar
from app.usuarios import Cuentas, ErrorUsuario, crear_token, leer_token

CLAVE = "clave-de-prueba-para-firmar-tokens-32"


@pytest.fixture
def cuentas():
    return Cuentas(conectar(":memory:"))


def test_primera_cuenta_es_admin_y_las_demas_pendientes(cuentas):
    dueña = cuentas.registrar("Dueña Stop 44", "dueña", "secreta123")
    vendedor = cuentas.registrar("Laura", "laura", "clave456")
    assert dueña.rol == "admin" and dueña.estado == "activo"
    assert vendedor.rol == "vendedor" and vendedor.estado == "pendiente"


def test_la_clave_se_guarda_cifrada(cuentas):
    cuentas.registrar("Dueña", "duena", "secreta123")
    guardada = cuentas.con.execute("SELECT clave_hash FROM usuarios").fetchone()[0]
    assert "secreta123" not in guardada and guardada.startswith("$2")


def test_ingresar(cuentas):
    cuentas.registrar("Dueña", "duena", "secreta123")
    assert cuentas.ingresar("DUENA", "secreta123").nombre == "Dueña"   # usuario sin importar mayúsculas
    with pytest.raises(ErrorUsuario, match="incorrectos"):
        cuentas.ingresar("duena", "mala")
    with pytest.raises(ErrorUsuario, match="incorrectos"):
        cuentas.ingresar("nadie", "secreta123")


def test_pendiente_no_ingresa_hasta_aprobar(cuentas):
    cuentas.registrar("Dueña", "duena", "secreta123")
    laura = cuentas.registrar("Laura", "laura", "clave456")
    with pytest.raises(ErrorUsuario, match="apruebe"):
        cuentas.ingresar("laura", "clave456")
    cuentas.actualizar(laura.id, estado="activo")
    assert cuentas.ingresar("laura", "clave456").id == laura.id
    cuentas.actualizar(laura.id, estado="inactivo")
    with pytest.raises(ErrorUsuario, match="desactivada"):
        cuentas.ingresar("laura", "clave456")


def test_validaciones_de_registro(cuentas):
    with pytest.raises(ErrorUsuario):
        cuentas.registrar("Ana", "a", "clave456")            # usuario muy corto
    with pytest.raises(ErrorUsuario):
        cuentas.registrar("Ana", "ana", "123")               # clave muy corta
    cuentas.registrar("Ana", "ana", "clave456")
    with pytest.raises(ErrorUsuario, match="ya existe"):
        cuentas.registrar("Otra Ana", "ANA", "clave789")


def test_siempre_queda_un_admin(cuentas):
    dueña = cuentas.registrar("Dueña", "duena", "secreta123")
    with pytest.raises(ErrorUsuario, match="al menos un administrador"):
        cuentas.actualizar(dueña.id, rol="vendedor")
    laura = cuentas.registrar("Laura", "laura", "clave456")
    cuentas.actualizar(laura.id, rol="admin", estado="activo")
    assert cuentas.actualizar(dueña.id, rol="vendedor").rol == "vendedor"


def test_cambiar_y_restablecer_clave(cuentas):
    u = cuentas.registrar("Dueña", "duena", "secreta123")
    with pytest.raises(ErrorUsuario):
        cuentas.cambiar_clave(u.id, "mala", "nueva123")
    cuentas.cambiar_clave(u.id, "secreta123", "nueva123")
    assert cuentas.ingresar("duena", "nueva123")
    cuentas.restablecer_clave(u.id, "otra1234")
    assert cuentas.ingresar("duena", "otra1234")


def test_token_de_sesion(cuentas):
    u = cuentas.registrar("Dueña", "duena", "secreta123")
    token = crear_token(u, CLAVE)
    assert leer_token(token, CLAVE) == u.id
    assert leer_token(token, "x" * 32) is None            # firma falsa
    assert leer_token(crear_token(u, CLAVE, dias=-1), CLAVE) is None  # vencido
    assert leer_token("basura", CLAVE) is None
