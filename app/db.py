"""Conexión y tablas de la base de datos SQLite.

Todo el dinero (costo, precio, total, recibido) se guarda en CENTAVOS de dólar
como número entero: $12,50 = 1250. Así no hay errores de redondeo.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre     TEXT NOT NULL,
    usuario    TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- con lo que ingresa
    clave_hash TEXT NOT NULL,                          -- contraseña cifrada (bcrypt)
    rol        TEXT NOT NULL DEFAULT 'vendedor' CHECK (rol IN ('admin', 'vendedor')),
    estado     TEXT NOT NULL DEFAULT 'pendiente'
               CHECK (estado IN ('activo', 'pendiente', 'inactivo')),
    creado     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS productos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre       TEXT    NOT NULL,
    categoria    TEXT    NOT NULL DEFAULT 'Otros',
    presentacion TEXT    NOT NULL DEFAULT '',          -- 750 ml, lata 330 ml...
    codigo       TEXT    UNIQUE,                       -- código de barras (opcional)
    costo        INTEGER NOT NULL DEFAULT 0 CHECK (costo >= 0),
    precio       INTEGER NOT NULL CHECK (precio > 0),
    stock        INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    minimo       INTEGER NOT NULL DEFAULT 5 CHECK (minimo >= 0),
    activo       INTEGER NOT NULL DEFAULT 1             -- 0 = eliminado
);

CREATE TABLE IF NOT EXISTS ventas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha       TEXT    NOT NULL,                      -- AAAA-MM-DD
    hora        TEXT    NOT NULL,                      -- HH:MM
    metodo      TEXT    NOT NULL,
    total       INTEGER NOT NULL,
    costo_total INTEGER NOT NULL DEFAULT 0,
    recibido    INTEGER,                               -- solo en efectivo
    anulada     INTEGER NOT NULL DEFAULT 0,
    usuario_id  INTEGER REFERENCES usuarios(id)        -- quién hizo la venta
);
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);

CREATE TABLE IF NOT EXISTS venta_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id    INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    nombre      TEXT    NOT NULL,                      -- nombre al momento de vender
    cantidad    INTEGER NOT NULL CHECK (cantidad > 0),
    precio      INTEGER NOT NULL,
    costo       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_items_venta ON venta_items(venta_id);

-- Fotos de los productos (en la misma base de datos, así un solo archivo guarda todo)
CREATE TABLE IF NOT EXISTS fotos (
    producto_id INTEGER PRIMARY KEY REFERENCES productos(id),
    imagen      BLOB    NOT NULL,                      -- la imagen ya achicada (JPEG, PNG o WEBP)
    tipo        TEXT    NOT NULL,                      -- image/jpeg, image/png, image/webp
    version     TEXT    NOT NULL                       -- cambia cada vez que se sube una foto nueva
);

-- Kardex: cada cambio de stock queda registrado
CREATE TABLE IF NOT EXISTS movimientos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    fecha       TEXT    NOT NULL,                      -- AAAA-MM-DD HH:MM:SS
    tipo        TEXT    NOT NULL
                CHECK (tipo IN ('inicial', 'entrada', 'ajuste', 'venta', 'anulacion')),
    cantidad    INTEGER NOT NULL,                      -- + suma, - resta
    stock_final INTEGER NOT NULL,
    nota        TEXT    NOT NULL DEFAULT '',
    usuario_id  INTEGER REFERENCES usuarios(id)
);
"""


def ruta_por_defecto() -> Path:
    """La ruta se puede cambiar con la variable de entorno STOP44_DB."""
    ruta = Path(os.getenv("STOP44_DB", "datos/stop44.db"))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return ruta


def _abrir(destino: str) -> sqlite3.Connection:
    con = sqlite3.connect(destino, check_same_thread=False, timeout=15)
    con.row_factory = sqlite3.Row          # filas accesibles por nombre: fila["precio"]
    con.execute("PRAGMA foreign_keys = ON")
    if destino != ":memory:":
        con.execute("PRAGMA journal_mode = WAL")   # varios pueden leer mientras otro escribe
    return con


def conectar(ruta: str | Path | None = None) -> sqlite3.Connection:
    """Abre UNA conexión y crea las tablas si no existen (útil en pruebas y scripts).

    Usa ruta=":memory:" para una base de datos temporal.
    """
    con = _abrir(":memory:" if ruta == ":memory:" else str(ruta or ruta_por_defecto()))
    con.executescript(ESQUEMA)
    return con


class BaseDeDatos:
    """Da a cada hilo del servidor su propia conexión al mismo archivo.

    Una conexión de SQLite no se puede usar desde dos hilos al mismo tiempo; si el
    servidor atiende varios pedidos a la vez, cada uno usa la suya y SQLite se
    encarga de que no se pisen.
    """

    def __init__(self, ruta: str | Path | None = None):
        self.ruta = ":memory:" if ruta == ":memory:" else str(ruta or ruta_por_defecto())
        self._local = threading.local()
        # En memoria (pruebas) no se puede abrir otra conexión a la misma base: se comparte una
        self._unica = conectar(":memory:") if self.ruta == ":memory:" else None
        if self._unica is None:
            conectar(self.ruta).close()            # crea las tablas una sola vez

    @property
    def con(self) -> sqlite3.Connection:
        if self._unica is not None:
            return self._unica
        if getattr(self._local, "con", None) is None:
            self._local.con = _abrir(self.ruta)
        return self._local.con


def tablas(con: sqlite3.Connection) -> list[str]:
    filas = con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    return [f["name"] for f in filas]
