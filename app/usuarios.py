"""Cuentas de usuario: registro, ingreso, roles y sesiones.

- Las contraseñas se guardan cifradas con bcrypt (nunca en texto plano).
- La primera cuenta que se registra queda como administradora y activa.
- Las siguientes quedan "pendientes" hasta que un administrador las apruebe.
- Al ingresar se entrega un token (JWT) que la app guarda para no pedir
  la contraseña cada vez.
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt

from .db import ruta_por_defecto
from .modelos import ROLES, Usuario
from .utils import ahora

DIAS_SESION = 30
_USUARIO_VALIDO = re.compile(r"^[a-z0-9._ñ]{3,30}$")
# hash falso para que un usuario inexistente tarde lo mismo que una clave mala
_HASH_FALSO = bcrypt.hashpw(b"no-existe", bcrypt.gensalt()).decode()


class ErrorUsuario(Exception):
    """Error con un mensaje listo para mostrar en la pantalla."""


# ---------------------------------------------------------------- contraseñas
def cifrar(clave: str) -> str:
    return bcrypt.hashpw(clave.encode(), bcrypt.gensalt()).decode()


def clave_correcta(clave: str, clave_hash: str) -> bool:
    try:
        return bcrypt.checkpw(clave.encode(), clave_hash.encode())
    except ValueError:
        return False


def _validar_clave(clave: str) -> None:
    if len(clave) < 6:
        raise ErrorUsuario("La contraseña debe tener al menos 6 caracteres.")
    if len(clave.encode()) > 72:
        raise ErrorUsuario("La contraseña es demasiado larga (máximo 72 caracteres).")


# ------------------------------------------------------------------- sesiones
def secreto() -> str:
    """Clave para firmar las sesiones: variable STOP44_SECRET o un archivo local."""
    if os.getenv("STOP44_SECRET"):
        return os.environ["STOP44_SECRET"]
    archivo = ruta_por_defecto().parent / ".secreto"     # junto a la base de datos (en Railway, en el volumen)
    if not archivo.exists():
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(secrets.token_hex(32))
    return archivo.read_text().strip()


def crear_token(u: Usuario, clave_firma: str, dias: int = DIAS_SESION) -> str:
    ahora = datetime.now(timezone.utc)
    datos = {"sub": str(u.id), "rol": u.rol, "iat": ahora, "exp": ahora + timedelta(days=dias)}
    return jwt.encode(datos, clave_firma, algorithm="HS256")


def leer_token(token: str, clave_firma: str) -> int | None:
    """Devuelve el id del usuario, o None si el token es falso o ya venció."""
    try:
        return int(jwt.decode(token, clave_firma, algorithms=["HS256"])["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


# ------------------------------------------------------------------- cuentas
class Cuentas:
    def __init__(self, fuente):
        """fuente: una BaseDeDatos (servidor) o una conexión directa (pruebas)."""
        self._fuente = fuente

    @property
    def con(self) -> sqlite3.Connection:
        return getattr(self._fuente, "con", self._fuente)

    @staticmethod
    def _usuario(f: sqlite3.Row) -> Usuario:
        return Usuario(id=f["id"], nombre=f["nombre"], usuario=f["usuario"], rol=f["rol"],
                       estado=f["estado"], creado=f["creado"])

    def obtener(self, usuario_id: int) -> Usuario | None:
        f = self.con.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        return self._usuario(f) if f else None

    def listar(self) -> list[Usuario]:
        filas = self.con.execute(
            "SELECT * FROM usuarios ORDER BY estado = 'pendiente' DESC, nombre").fetchall()
        return [self._usuario(f) for f in filas]

    def hay_usuarios(self) -> bool:
        return self.con.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone() is not None

    def registrar(self, nombre: str, usuario: str, clave: str) -> Usuario:
        nombre, usuario = nombre.strip(), usuario.strip().lower()
        if len(nombre) < 2:
            raise ErrorUsuario("Escribe tu nombre.")
        if not _USUARIO_VALIDO.match(usuario):
            raise ErrorUsuario("El usuario debe tener de 3 a 30 caracteres: letras, números, punto o guion bajo, sin espacios.")
        _validar_clave(clave)
        primero = not self.hay_usuarios()
        rol, estado = ("admin", "activo") if primero else ("vendedor", "pendiente")
        try:
            with self.con:
                cur = self.con.execute(
                    "INSERT INTO usuarios (nombre, usuario, clave_hash, rol, estado, creado)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (nombre, usuario, cifrar(clave), rol, estado, ahora().strftime("%Y-%m-%d %H:%M:%S")))
        except sqlite3.IntegrityError:
            raise ErrorUsuario("Ese usuario ya existe. Prueba con otro.") from None
        return self.obtener(cur.lastrowid)

    def ingresar(self, usuario: str, clave: str) -> Usuario:
        f = self.con.execute(
            "SELECT * FROM usuarios WHERE usuario = ?", (usuario.strip().lower(),)).fetchone()
        if not clave_correcta(clave, f["clave_hash"] if f else _HASH_FALSO) or f is None:
            raise ErrorUsuario("Usuario o contraseña incorrectos.")
        u = self._usuario(f)
        if u.estado == "pendiente":
            raise ErrorUsuario("Tu cuenta está esperando que un administrador la apruebe.")
        if u.estado == "inactivo":
            raise ErrorUsuario("Tu cuenta está desactivada. Habla con la administradora.")
        return u

    def cambiar_clave(self, usuario_id: int, actual: str, nueva: str) -> None:
        f = self.con.execute("SELECT clave_hash FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if not f or not clave_correcta(actual, f["clave_hash"]):
            raise ErrorUsuario("La contraseña actual no es correcta.")
        _validar_clave(nueva)
        with self.con:
            self.con.execute("UPDATE usuarios SET clave_hash = ? WHERE id = ?", (cifrar(nueva), usuario_id))

    # ------------------------------------------------- acciones del administrador
    def _admins_activos(self) -> int:
        return self.con.execute(
            "SELECT COUNT(*) FROM usuarios WHERE rol = 'admin' AND estado = 'activo'").fetchone()[0]

    def actualizar(self, usuario_id: int, rol: str | None = None, estado: str | None = None) -> Usuario:
        """Aprobar (estado='activo'), desactivar (estado='inactivo') o cambiar el rol."""
        u = self.obtener(usuario_id)
        if u is None:
            raise ErrorUsuario("Ese usuario no existe.")
        if rol is not None and rol not in ROLES:
            raise ErrorUsuario("Rol no válido.")
        if estado is not None and estado not in ("activo", "pendiente", "inactivo"):
            raise ErrorUsuario("Estado no válido.")
        nuevo_rol, nuevo_estado = rol or u.rol, estado or u.estado
        deja_de_ser_admin = u.es_admin and u.activo and not (nuevo_rol == "admin" and nuevo_estado == "activo")
        if deja_de_ser_admin and self._admins_activos() <= 1:
            raise ErrorUsuario("Debe quedar al menos un administrador activo.")
        with self.con:
            self.con.execute("UPDATE usuarios SET rol = ?, estado = ? WHERE id = ?",
                             (nuevo_rol, nuevo_estado, usuario_id))
        return self.obtener(usuario_id)

    def restablecer_clave(self, usuario_id: int, nueva: str) -> None:
        """El administrador le pone una contraseña nueva a alguien que la olvidó."""
        if self.obtener(usuario_id) is None:
            raise ErrorUsuario("Ese usuario no existe.")
        _validar_clave(nueva)
        with self.con:
            self.con.execute("UPDATE usuarios SET clave_hash = ? WHERE id = ?", (cifrar(nueva), usuario_id))
