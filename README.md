# 🛑 Stop 44 — Inventario y Ventas

App para la licorería **Stop 44** (Ecuador): vender, controlar el inventario, ver las ventas del día y el resumen del negocio, con cuentas para la administradora y los vendedores. Se instala en el celular como una app.

- **Backend:** Python · FastAPI · SQLite
- **Frontend:** HTML, CSS y JavaScript, sin frameworks. Estilo "Muro", sacado del logo de la tienda
- **App:** PWA instalable en Android, iPhone y computador
- **Publicada en:** Railway

## Lo que hace

| Pantalla | Quién la ve | Qué hace |
|---|---|---|
| **Ingresar / Crear cuenta** | Todos | La primera cuenta es la del administrador; las siguientes esperan aprobación |
| **Vender** | Todos | Buscar o escanear códigos de barras, carrito, cobro en efectivo (con vueltas), Deuna o **fiado** a un cliente |
| **Inventario** | Administrador | Productos con foto, costo, precio y margen, entradas de mercancía, conteo físico, historial (kardex); escanear una botella en el buscador la abre o propone crearla |
| **Ventas** | Todos (el vendedor solo ve las suyas) | Ventas de cualquier día, efectivo / Deuna / fiado, efectivo en caja (con abonos), anulaciones, cierre para WhatsApp y Excel |
| **Fiados** | Todos | Clientes que deben, su cuenta, abonos (todo o una parte) y recordatorio por WhatsApp |
| **Resumen** | Administrador | Ventas por día y por hora, comparación con el periodo anterior, más vendidos, lo que hay que pedir |
| **Usuarios** | Administrador | Aprobar cuentas, roles, contraseñas y copia de seguridad |

**Lector de código de barras:** los lectores USB o Bluetooth funcionan como un teclado (escriben el
número y presionan Enter). En **Vender** se escanea en el buscador; en el formulario del producto, el
Enter del lector no guarda: pasa al campo que falta, y avisa si el código ya es de otro producto.

Detalles técnicos que vale la pena saber:
- El **dinero se guarda en centavos** (enteros) para no tener errores de redondeo: `$12,50` = `1250`.
- Las fechas van siempre en **hora de Ecuador** (`zoneinfo`), sin importar dónde esté el servidor.
- Las contraseñas se guardan **cifradas con bcrypt**, y la sesión es un **JWT** en una cookie `HttpOnly`.
- Cada cambio de stock queda en la tabla `movimientos` (**kardex**).
- Las fotos se guardan dentro de la misma base de datos, así todo queda en un solo archivo.
- Lo que debe un cliente no se guarda como un número: se calcula siempre (fiado − abonos), así nunca se descuadra. Si se anula una venta fiada o un abono, la deuda se ajusta sola.
- La base de datos se actualiza sola al arrancar (migraciones en `app/db.py`), sin perder datos.

## Estructura

```
stop44-licoreria/
├── main.py              # entrada para Railway (trae app/main.py)
├── app/                 # backend
│   ├── main.py          # API con FastAPI: rutas, permisos y sesión
│   ├── servicios.py     # reglas del negocio (clase Tienda): ventas, inventario, fiados
│   ├── reporte.py       # Excel de ventas
│   ├── usuarios.py      # cuentas, roles, bcrypt y JWT
│   ├── db.py            # tablas SQLite y una conexión por hilo
│   ├── modelos.py       # dataclasses: Producto, Venta, Usuario...
│   └── utils.py         # dinero, fechas de Ecuador y búsqueda sin tildes
├── web/                 # frontend
│   ├── index.html
│   ├── manifest.json    # datos de la app instalable
│   ├── sw.js            # service worker
│   ├── css/estilos.css
│   ├── js/              # una pantalla por archivo
│   └── img/             # logo, íconos y ladrillo
└── tests/               # pruebas con pytest
```

## Correrla en el PC

```bash
python -m venv .venv
source .venv/Scripts/activate        # en Windows con Git Bash
pip install -r requirements.txt
pytest                               # deben pasar todas
uvicorn app.main:app --reload
```

Después abre http://127.0.0.1:8000. La documentación de la API está en http://127.0.0.1:8000/docs. La base de datos de prueba queda en `datos/`, que no se sube a GitHub.

## Publicarla en Railway

1. Entra a [railway.com](https://railway.com) con tu cuenta de GitHub.
2. **New Project → Deploy from GitHub repo** y elige `stop44-licoreria`. Railway detecta Python y FastAPI solo.
3. **Agrega un volumen**, el disco donde se guardan las ventas y que no se borra: clic derecho en el proyecto (o `Ctrl + K`) → **Volume**. Conéctalo al servicio con la ruta de montaje **`/data`**. La app lo encuentra sola.
4. En **Variables** del servicio agrega `FORWARDED_ALLOW_IPS` con el valor `*`. Así la app sabe que está detrás del HTTPS de Railway y protege la sesión.
5. En **Settings → Networking → Generate Domain** se crea el enlace de la app.
6. *(Opcional)* En **Settings → Deploy → Healthcheck Path** pon `/api/salud`.
7. **Apenas esté arriba, abre el enlace y crea la cuenta del administrador.** La primera cuenta que se crea queda como administrador.

Cada `git push` a `main` actualiza la app sola.

## Instalarla en el celular

- **Android (Chrome):** abre el enlace y toca **Instalar app**, o usa el menú ⋮ → *Instalar aplicación*.
- **iPhone (Safari):** botón **Compartir** → **Agregar a inicio**.

## Reporte en Excel

En **Ventas**, **Resumen** o **Usuarios** → **Excel**. Se genera al momento con hojas Resumen, Por día, Por semana, Por mes, Productos, Fiados, Ventas, Abonos, Detalle e Inventario. Los totales son fórmulas de Excel.

## Copias de seguridad

En **Usuarios → Copia de seguridad** se descarga un archivo `.db` con todo. Guárdalo de vez en cuando en el computador o en Google Drive. Railway también tiene respaldos del volumen en su panel.

## Ideas para después

- [ ] Apertura y cierre de caja con conteo de billetes
- [ ] Gastos del día (hielo, transporte, servicios)
- [ ] Proveedores y pedidos automáticos
- [ ] Combos y promociones
- [ ] Exportar ventas a Excel
