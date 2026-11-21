"""Punto de entrada para Railway.

Railway detecta FastAPI y arranca con:  uvicorn main:app --host 0.0.0.0 --port $PORT
Este archivo solo trae la app real, que vive en app/main.py.
En tu PC puedes seguir usando:  uvicorn app.main:app --reload
"""

from app.main import app  # noqa: F401
