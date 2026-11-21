"""Funciones de ayuda: formato de dinero, fechas y texto.

El dinero se guarda SIEMPRE en centavos (números enteros) para no tener errores
de redondeo: $12,50 se guarda como 1250.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def dinero(centavos: int | None) -> str:
    """Formatea centavos en dólares: 1250 -> '$12,50' y 123450 -> '$1.234,50'."""
    n = round(centavos or 0)
    signo = "-" if n < 0 else ""
    dolares, cents = divmod(abs(n), 100)
    return f"{signo}${dolares:,}".replace(",", ".") + f",{cents:02d}"


def a_centavos(texto: str | int | float | None) -> int:
    """Convierte lo que escribe el usuario en centavos.

    '12,50' -> 1250   '12.50' -> 1250   '$12' -> 1200   '1.234,50' -> 123450
    """
    if isinstance(texto, (int, float)):
        return round(texto * 100)
    t = re.sub(r"[^\d,.]", "", str(texto or ""))
    if not t:
        return 0
    if "," in t:                                   # coma = centavos, punto = miles
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") == 1 and len(t.split(".")[1]) <= 2:
        pass                                       # 12.50 también se entiende
    else:
        t = t.replace(".", "")                     # 1.234 = mil doscientos treinta y cuatro
    return round(float(t) * 100)


def normalizar(texto: str | None) -> str:
    """Minúsculas y sin tildes, para buscar sin importar cómo se escriba."""
    t = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def hoy() -> str:
    return date.today().isoformat()


def sumar_dias(fecha: str, dias: int) -> str:
    return (date.fromisoformat(fecha) + timedelta(days=dias)).isoformat()


def fecha_larga(fecha: str) -> str:
    d = date.fromisoformat(fecha)
    return f"{DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def fecha_corta(fecha: str) -> str:
    d = date.fromisoformat(fecha)
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def ahora() -> datetime:
    return datetime.now()
