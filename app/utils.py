"""Funciones de ayuda: formato de pesos, fechas y texto."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def cop(valor: float | int | None) -> str:
    """Formatea un valor en pesos colombianos: 12500 -> '$12.500'."""
    n = round(valor or 0)
    signo = "-" if n < 0 else ""
    return f"{signo}${abs(n):,}".replace(",", ".")


def a_entero(texto: str | int | None) -> int:
    """Convierte lo que escribe el usuario ('$12.500', '12500') en entero."""
    if isinstance(texto, int):
        return texto
    digitos = re.sub(r"[^\d]", "", str(texto or ""))
    return int(digitos) if digitos else 0


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
