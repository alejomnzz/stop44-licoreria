"""API de Stop 44 con FastAPI.

Ejecutar:  uvicorn app.main:app --reload
Documentación interactiva:  http://127.0.0.1:8000/docs

Importante: todo el dinero viaja en CENTAVOS de dólar. $12,50 = 1250.
"""

from __future__ import annotations

import base64
import binascii
import os
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .modelos import CATEGORIAS, METODOS_PAGO, Producto, Usuario, Venta
from .servicios import ErrorTienda, Tienda
from .usuarios import (DIAS_SESION, Cuentas, ErrorUsuario, crear_token, leer_token,
                       secreto)
from .utils import hoy


COOKIE = "stop44_sesion"
CARPETA_WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Stop 44", description="Inventario y ventas de la licorería Stop 44")

tienda = Tienda()                       # abre datos/stop44.db (o la ruta de STOP44_DB)
cuentas = Cuentas(tienda.con)           # comparten la misma conexión
CLAVE_FIRMA = secreto()


# ------------------------------------------------------------------ errores
@app.exception_handler(ErrorTienda)
@app.exception_handler(ErrorUsuario)
async def error_de_negocio(_: Request, exc: Exception):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ------------------------------------------------------------------- sesión
def usuario_actual(request: Request) -> Usuario:
    token = request.cookies.get(COOKIE)
    auth = request.headers.get("Authorization", "")
    if not token and auth.startswith("Bearer "):
        token = auth[7:]
    usuario_id = leer_token(token, CLAVE_FIRMA) if token else None
    u = cuentas.obtener(usuario_id) if usuario_id else None
    if u is None or not u.activo:
        raise HTTPException(401, "Debes ingresar.")
    return u


def solo_admin(u: Annotated[Usuario, Depends(usuario_actual)]) -> Usuario:
    if not u.es_admin:
        raise HTTPException(403, "Solo un administrador puede hacer esto.")
    return u


Actual = Annotated[Usuario, Depends(usuario_actual)]
Admin = Annotated[Usuario, Depends(solo_admin)]


def _abrir_sesion(response: Response, request: Request, u: Usuario) -> None:
    response.set_cookie(
        COOKIE, crear_token(u, CLAVE_FIRMA), max_age=DIAS_SESION * 86400, httponly=True,
        samesite="lax", secure=request.url.scheme == "https")


# ------------------------------------------------------------- conversiones
def usuario_json(u: Usuario) -> dict:
    return {"id": u.id, "nombre": u.nombre, "usuario": u.usuario, "rol": u.rol,
            "estado": u.estado, "creado": u.creado}


def producto_json(p: Producto, ver_costos: bool) -> dict:
    d = asdict(p) | {"nombre_completo": p.nombre_completo, "stock_bajo": p.stock_bajo,
                     "agotado": p.agotado, "margen": p.margen}
    if not ver_costos:
        d.pop("costo"), d.pop("margen")
    return d


def venta_json(v: Venta, ver_costos: bool) -> dict:
    d = asdict(v) | {"vueltas": v.vueltas, "ganancia": v.ganancia}
    if not ver_costos:
        d.pop("costo_total"), d.pop("ganancia")
        for i in d["items"]:
            i.pop("costo")
    return d


# ------------------------------------------------------------ datos de entrada
class Registro(BaseModel):
    nombre: str
    usuario: str
    clave: str


class Ingreso(BaseModel):
    usuario: str
    clave: str


class CambioClave(BaseModel):
    actual: str
    nueva: str


class ClaveNueva(BaseModel):
    nueva: str


class CambioUsuario(BaseModel):
    rol: str | None = None
    estado: str | None = None


class ProductoEntrada(BaseModel):
    """precio y costo en centavos: $12,50 = 1250"""
    nombre: str
    precio: int = Field(gt=0)
    categoria: str = "Otros"
    presentacion: str = ""
    codigo: str | None = None
    costo: int = Field(0, ge=0)
    stock: int = Field(0, ge=0)
    minimo: int = Field(5, ge=0)


class FotoEntrada(BaseModel):
    """La foto ya achicada por la app, en base64 (puede venir como data:image/jpeg;base64,...)"""
    imagen: str


class Entrada(BaseModel):
    cantidad: int = Field(ge=0)
    costo: int | None = Field(None, ge=0)
    fijar: bool = False


class ItemCarrito(BaseModel):
    producto_id: int
    cantidad: int = Field(gt=0)


class NuevaVenta(BaseModel):
    """recibido: dinero que entregó el cliente en efectivo, en centavos"""
    items: list[ItemCarrito]
    metodo: str
    recibido: int | None = None


# -------------------------------------------------------------------- cuentas
@app.get("/api/auth/estado", tags=["Cuentas"])
async def estado():
    """Si todavía no hay usuarios, la app muestra "Crear cuenta de administradora"."""
    return {"hay_usuarios": cuentas.hay_usuarios()}


@app.post("/api/auth/registro", tags=["Cuentas"])
async def registrarse(datos: Registro, request: Request, response: Response):
    u = cuentas.registrar(datos.nombre, datos.usuario, datos.clave)
    if u.activo:                       # la primera cuenta entra de una vez
        _abrir_sesion(response, request, u)
        return {"usuario": usuario_json(u), "mensaje": "¡Bienvenida! Eres la administradora."}
    return {"usuario": usuario_json(u),
            "mensaje": "Cuenta creada. Un administrador debe aprobarla antes de que puedas ingresar."}


@app.post("/api/auth/ingresar", tags=["Cuentas"])
async def ingresar(datos: Ingreso, request: Request, response: Response):
    u = cuentas.ingresar(datos.usuario, datos.clave)
    _abrir_sesion(response, request, u)
    return {"usuario": usuario_json(u)}


@app.post("/api/auth/salir", tags=["Cuentas"])
async def salir(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/auth/yo", tags=["Cuentas"])
async def yo(u: Actual):
    return usuario_json(u)


@app.post("/api/auth/clave", tags=["Cuentas"])
async def cambiar_mi_clave(datos: CambioClave, u: Actual):
    cuentas.cambiar_clave(u.id, datos.actual, datos.nueva)
    return {"ok": True}


@app.get("/api/usuarios", tags=["Cuentas"])
async def listar_usuarios(_: Admin):
    return [usuario_json(u) for u in cuentas.listar()]


@app.patch("/api/usuarios/{usuario_id}", tags=["Cuentas"])
async def actualizar_usuario(usuario_id: int, datos: CambioUsuario, _: Admin):
    """Aprobar (estado=activo), desactivar (estado=inactivo) o cambiar el rol."""
    return usuario_json(cuentas.actualizar(usuario_id, datos.rol, datos.estado))


@app.post("/api/usuarios/{usuario_id}/clave", tags=["Cuentas"])
async def restablecer_clave(usuario_id: int, datos: ClaveNueva, _: Admin):
    cuentas.restablecer_clave(usuario_id, datos.nueva)
    return {"ok": True}


# ------------------------------------------------------------------ productos
@app.get("/api/catalogo", tags=["Productos"])
async def catalogo():
    return {"categorias": CATEGORIAS, "metodos_pago": METODOS_PAGO}


@app.get("/api/productos", tags=["Productos"])
async def listar_productos(u: Actual, buscar: str = "", categoria: str | None = None,
                           solo_bajo: bool = False):
    return [producto_json(p, u.es_admin) for p in tienda.productos(buscar, categoria, solo_bajo)]


@app.get("/api/productos/codigo/{codigo}", tags=["Productos"])
async def por_codigo(codigo: str, u: Actual):
    p = tienda.por_codigo(codigo)
    if p is None:
        raise HTTPException(404, "No hay ningún producto con ese código.")
    return producto_json(p, u.es_admin)


@app.post("/api/productos", tags=["Productos"], status_code=201)
async def crear_producto(datos: ProductoEntrada, u: Admin):
    return producto_json(tienda.guardar_producto(Producto(**datos.model_dump()), u.id), True)


@app.put("/api/productos/{producto_id}", tags=["Productos"])
async def editar_producto(producto_id: int, datos: ProductoEntrada, u: Admin):
    if tienda.producto(producto_id) is None:
        raise HTTPException(404, "El producto no existe.")
    p = Producto(**datos.model_dump(), id=producto_id)
    return producto_json(tienda.guardar_producto(p, u.id), True)


@app.delete("/api/productos/{producto_id}", tags=["Productos"])
async def eliminar_producto(producto_id: int, _: Admin):
    tienda.eliminar_producto(producto_id)
    return {"ok": True}


@app.post("/api/productos/{producto_id}/entrada", tags=["Productos"])
async def entrada_mercancia(producto_id: int, datos: Entrada, u: Admin):
    """Llegada de mercancía (suma) o conteo físico (fijar=true)."""
    p = tienda.entrada(producto_id, datos.cantidad, datos.costo, datos.fijar, u.id)
    return producto_json(p, True)


@app.put("/api/productos/{producto_id}/foto", tags=["Productos"])
async def subir_foto(producto_id: int, datos: FotoEntrada, _: Admin):
    texto = datos.imagen.split(",", 1)[-1]          # quita el "data:image/jpeg;base64,"
    try:
        imagen = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "La foto llegó dañada. Intenta de nuevo.") from None
    tienda.guardar_foto(producto_id, imagen)
    return producto_json(tienda.producto(producto_id), True)


@app.delete("/api/productos/{producto_id}/foto", tags=["Productos"])
async def quitar_foto(producto_id: int, _: Admin):
    tienda.quitar_foto(producto_id)
    return {"ok": True}


@app.get("/api/productos/{producto_id}/foto", tags=["Productos"])
async def ver_foto(producto_id: int, _: Actual):
    foto = tienda.foto(producto_id)
    if foto is None:
        raise HTTPException(404, "Ese producto no tiene foto.")
    imagen, tipo = foto
    # la dirección lleva ?v=<versión>, así que el navegador la puede guardar mucho tiempo
    return Response(imagen, media_type=tipo, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@app.get("/api/productos/{producto_id}/movimientos", tags=["Productos"])
async def movimientos(producto_id: int, _: Admin):
    """Historial de cambios de stock (kardex) del producto."""
    return tienda.movimientos(producto_id)


@app.get("/api/inventario/valor", tags=["Productos"])
async def valor_inventario(_: Admin):
    unidades, costo, venta = tienda.valor_inventario()
    return {"unidades": unidades, "a_costo": costo, "a_precio_venta": venta}


# --------------------------------------------------------------------- ventas
@app.post("/api/ventas", tags=["Ventas"], status_code=201)
async def vender(datos: NuevaVenta, u: Actual):
    items: dict[int, int] = {}
    for i in datos.items:
        items[i.producto_id] = items.get(i.producto_id, 0) + i.cantidad
    v = tienda.registrar_venta(items, datos.metodo, datos.recibido, u.id)
    return venta_json(v, u.es_admin)


@app.get("/api/ventas", tags=["Ventas"])
async def ventas_del_dia(u: Actual, fecha: str | None = None):
    """El administrador ve todas; el vendedor solo las suyas."""
    lista = tienda.ventas_del_dia(fecha or hoy(), None if u.es_admin else u.id)
    return [venta_json(v, u.es_admin) for v in lista]


@app.post("/api/ventas/{venta_id}/anular", tags=["Ventas"])
async def anular(venta_id: int, u: Admin):
    tienda.anular_venta(venta_id, u.id)
    return venta_json(tienda.venta(venta_id), True)


# ------------------------------------------------------------------- reportes
@app.get("/api/resumen", tags=["Reportes"])
async def resumen(_: Admin, desde: str | None = None, hasta: str | None = None):
    r = tienda.resumen(desde or hoy(), hasta)
    return asdict(r) | {"promedio": r.promedio}


@app.get("/api/resumen/dias", tags=["Reportes"])
async def totales_por_dia(desde: str, hasta: str, _: Admin):
    return tienda.totales_por_dia(desde, hasta)


@app.get("/api/stock-bajo", tags=["Reportes"])
async def stock_bajo(u: Actual):
    return [producto_json(p, u.es_admin) for p in tienda.stock_bajo()]


@app.get("/api/cierre", tags=["Reportes"])
async def cierre(_: Admin, fecha: str | None = None):
    return {"texto": tienda.texto_cierre(fecha or hoy())}


# ---------------------------------------------------------------- frontend
if (CARPETA_WEB / "index.html").exists():
    app.mount("/", StaticFiles(directory=CARPETA_WEB, html=True), name="web")
else:
    @app.get("/", include_in_schema=False)
    async def inicio():
        return {"app": "Stop 44", "estado": "API funcionando", "documentacion": "/docs"}
