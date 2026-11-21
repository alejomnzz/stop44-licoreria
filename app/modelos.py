"""Clases de datos del negocio."""

from __future__ import annotations

from dataclasses import dataclass, field

CATEGORIAS = [
    "Aguardiente", "Ron", "Whisky", "Cerveza", "Vino", "Vodka", "Tequila",
    "Ginebra", "Gaseosas y aguas", "Energizantes", "Snacks", "Cigarrillos",
    "Hielo", "Otros",
]
METODOS_PAGO = ["Efectivo", "Deuna", "Fiado"]
METODOS_ABONO = ["Efectivo", "Deuna"]          # con qué puede pagar un cliente lo que debe
ROLES = ["admin", "vendedor"]


@dataclass
class Usuario:
    nombre: str
    usuario: str
    rol: str = "vendedor"
    estado: str = "pendiente"
    creado: str = ""
    id: int | None = None

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"

    @property
    def activo(self) -> bool:
        return self.estado == "activo"


@dataclass
class Producto:
    """Los valores de dinero (precio, costo) van en centavos: $12,50 = 1250."""
    nombre: str
    precio: int
    categoria: str = "Otros"
    presentacion: str = ""
    codigo: str | None = None
    costo: int = 0
    stock: int = 0
    minimo: int = 5
    foto: str | None = None            # versión de la foto, o None si no tiene
    id: int | None = None

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.presentacion}".strip()

    @property
    def stock_bajo(self) -> bool:
        return self.stock <= self.minimo

    @property
    def agotado(self) -> bool:
        return self.stock <= 0

    @property
    def margen(self) -> int | None:
        """Porcentaje de ganancia sobre el precio de venta."""
        if not self.precio or not self.costo:
            return None
        return round((self.precio - self.costo) / self.precio * 100)


@dataclass
class ItemVenta:
    producto_id: int
    nombre: str
    cantidad: int
    precio: int
    costo: int = 0

    @property
    def subtotal(self) -> int:
        return self.cantidad * self.precio


@dataclass
class Venta:
    fecha: str
    hora: str
    metodo: str
    total: int
    costo_total: int
    items: list[ItemVenta] = field(default_factory=list)
    recibido: int | None = None
    anulada: bool = False
    usuario_id: int | None = None
    vendedor: str = ""                 # nombre de quien vendió (para mostrar)
    cliente_id: int | None = None      # solo si fue fiado
    cliente: str = ""
    id: int | None = None

    @property
    def ganancia(self) -> int:
        return self.total - self.costo_total

    @property
    def vueltas(self) -> int:
        return max(0, (self.recibido or 0) - self.total)


@dataclass
class ProductoVendido:
    nombre: str
    cantidad: int
    total: int


@dataclass
class ResumenDia:
    fecha: str
    total: int = 0
    num_ventas: int = 0
    ganancia: int = 0
    por_metodo: dict[str, int] = field(default_factory=dict)
    por_vendedor: dict[str, int] = field(default_factory=dict)
    abonos: dict[str, int] = field(default_factory=dict)      # pagos de fiados recibidos, por método
    productos: list[ProductoVendido] = field(default_factory=list)

    @property
    def promedio(self) -> int:
        return round(self.total / self.num_ventas) if self.num_ventas else 0


@dataclass
class Cliente:
    nombre: str
    telefono: str = ""
    nota: str = ""
    creado: str = ""
    fiado: int = 0          # todo lo que ha llevado fiado (centavos)
    abonado: int = 0        # todo lo que ha pagado
    ultimo_movimiento: str = ""
    id: int | None = None

    @property
    def saldo(self) -> int:
        """Lo que debe hoy."""
        return self.fiado - self.abonado
