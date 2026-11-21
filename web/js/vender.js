// Pantalla de Vender: buscar o escanear productos, armar la venta y cobrar.
// En el celular el carrito es una barra abajo que se abre como hoja;
// en el computador es un panel fijo a la derecha.

import { api } from "./api.js";
import { $, esc, dinero, aCentavos, avisar, celebrar, cargando } from "./ui.js";
import { dibujoProducto } from "./dibujos.js";

const BILLETES = [500, 1000, 2000, 5000];    // $5, $10, $20, $50 en centavos
const ICONO_EFECTIVO = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 10v4M18 10v4"/></svg>';
const ICONO_DEUNA = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><path d="M14 14h3v3M21 14v7h-4M14 18v3"/></svg>';

// El carrito vive aquí para no perderse al cambiar de pantalla
const estado = {
  productos: [],
  carrito: new Map(),      // producto_id -> cantidad
  categoria: "Todo",
  buscar: "",
  metodo: "Efectivo",
  recibido: "",
  cobrando: false,
};

let raiz = null;

const producto = (id) => estado.productos.find((p) => p.id === id);
const unidades = () => [...estado.carrito.values()].reduce((a, b) => a + b, 0);
const total = () => [...estado.carrito].reduce((s, [id, c]) => s + (producto(id)?.precio || 0) * c, 0);

export async function mostrarVender(el) {
  raiz = el;
  el.innerHTML = cargando();
  try {
    estado.productos = await api.get("/api/productos");
  } catch (e) {
    el.innerHTML = `<div class="panel-roto vacio"><p>${esc(e.message)}</p><button class="btn btn-rojo" id="reintentar">Intentar de nuevo</button></div>`;
    $("#reintentar", el).onclick = () => mostrarVender(el);
    return;
  }
  // quitar del carrito lo que ya no existe
  for (const id of estado.carrito.keys()) if (!producto(id)) estado.carrito.delete(id);

  el.innerHTML = `<div class="pantalla-vender">
    <div class="vender">
      <section class="vender-productos">
        <h1 class="titulo">Vender</h1>
        <label class="buscador">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>
          <input id="buscar" type="search" placeholder="Buscar o escanear código" autocomplete="off" value="${esc(estado.buscar)}" aria-label="Buscar producto o escanear código de barras">
        </label>
        <div class="categorias" id="categorias" role="tablist"></div>
        <div class="productos" id="productos"></div>
      </section>
      <aside class="carrito" id="carrito" aria-label="Venta actual"></aside>
    </div>
    <button class="barra-carrito" id="barra-carrito" aria-controls="carrito"></button>
    <div class="velo" id="velo"></div>
  </div>`;

  pintarCategorias();
  pintarProductos();
  pintarCarrito();
  conectarEventos();
  if (window.matchMedia("(min-width: 900px)").matches) $("#buscar", el).focus();
}

// ---------- Productos ----------
function pintarCategorias() {
  const presentes = [...new Set(estado.productos.map((p) => p.categoria))].sort();
  if (!presentes.includes(estado.categoria)) estado.categoria = "Todo";
  $("#categorias", raiz).innerHTML = ["Todo", ...presentes].map((c) =>
    `<button class="chip ${c === estado.categoria ? "activo" : ""}" data-categoria="${esc(c)}" role="tab" aria-selected="${c === estado.categoria}">${esc(c)}</button>`).join("");
}

const sinTildes = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function pintarProductos() {
  const caja = $("#productos", raiz);
  if (!estado.productos.length) {
    caja.innerHTML = `<div class="panel-roto vacio sin-productos"><p>Todavía no hay productos. Agrégalos en Inventario para empezar a vender.</p></div>`;
    return;
  }
  const q = sinTildes(estado.buscar.trim());
  const lista = estado.productos.filter((p) =>
    (estado.categoria === "Todo" || p.categoria === estado.categoria) &&
    (!q || sinTildes(`${p.nombre} ${p.presentacion} ${p.categoria} ${p.codigo || ""}`).includes(q)));
  if (!lista.length) {
    caja.innerHTML = `<p class="nada">No hay productos con “${esc(estado.buscar)}”.</p>`;
    return;
  }
  caja.innerHTML = lista.map((p) => {
    const enCarrito = estado.carrito.get(p.id) || 0;
    const quedan = p.stock - enCarrito;
    const etiqueta = p.stock <= 0 ? '<span class="etiqueta roja">Agotado</span>'
      : `<span class="etiqueta ${p.stock_bajo ? "roja" : ""}">${quedan}</span>`;
    return `
      <button class="producto ${p.stock <= 0 ? "agotado" : ""}" data-id="${p.id}" ${p.stock <= 0 ? 'aria-disabled="true"' : ""}
              aria-label="${esc(p.nombre_completo)}, ${dinero(p.precio)}, quedan ${p.stock}">
        <span class="producto-stock">${etiqueta}</span>
        ${enCarrito ? `<span class="producto-cuenta">${enCarrito}</span>` : ""}
        <span class="dibujo">${dibujoProducto(p.categoria)}</span>
        <b>${esc(p.nombre)}</b>
        <span class="tenue">${esc(p.presentacion)}</span>
        <span class="precio">${dinero(p.precio)}</span>
      </button>`;
  }).join("");
}

function agregar(id, boton) {
  const p = producto(id);
  if (!p) return;
  const actual = estado.carrito.get(id) || 0;
  if (actual + 1 > p.stock) {
    avisar(p.stock <= 0 ? `${p.nombre_completo} está agotado.` : `Solo hay ${p.stock} de ${p.nombre_completo}.`, "error");
    return;
  }
  estado.carrito.set(id, actual + 1);
  if (boton) volarAlCarrito(boton);
  pintarProductos();
  pintarCarrito(true);
}

function cambiar(id, delta) {
  const p = producto(id);
  const nueva = (estado.carrito.get(id) || 0) + delta;
  if (delta > 0 && nueva > p.stock) { avisar(`Solo hay ${p.stock} de ${p.nombre_completo}.`, "error"); return; }
  if (nueva <= 0) estado.carrito.delete(id); else estado.carrito.set(id, nueva);
  pintarProductos();
  pintarCarrito();
}

// El octágono rojo vuela desde el producto hasta el carrito
function volarAlCarrito(boton) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const destino = window.matchMedia("(min-width: 900px)").matches ? $("#carrito", raiz) : $("#barra-carrito", raiz);
  const a = boton.getBoundingClientRect(), b = destino.getBoundingClientRect();
  const ficha = document.createElement("div");
  ficha.className = "ficha-vuela";
  ficha.style.left = `${a.left + a.width / 2 - 16}px`;
  ficha.style.top = `${a.top + a.height / 2 - 16}px`;
  document.body.appendChild(ficha);
  const dx = b.left + b.width / 2 - (a.left + a.width / 2);
  const dy = b.top + Math.min(b.height / 2, 40) - (a.top + a.height / 2);
  ficha.animate(
    [{ transform: "translate(0,0) scale(1) rotate(0)" }, { transform: `translate(${dx}px,${dy}px) scale(.4) rotate(200deg)`, opacity: 0.4 }],
    { duration: 520, easing: "cubic-bezier(.5,-0.4,.6,1)" }
  ).onfinish = () => ficha.remove();
}

// ---------- Carrito ----------
function pintarCarrito(sacudir = false) {
  const n = unidades(), t = total();
  const barra = $("#barra-carrito", raiz);
  barra.hidden = n === 0;
  barra.innerHTML = `<span><small>${n} ${n === 1 ? "producto" : "productos"}</small><b>${dinero(t)}</b></span><span class="btn btn-rojo">Cobrar</span>`;
  if (sacudir) { barra.classList.remove("salta"); void barra.offsetWidth; barra.classList.add("salta"); }

  const caja = $("#carrito", raiz);
  if (!n) {
    caja.classList.remove("abierto");
    $("#velo", raiz).classList.remove("visible");
    caja.innerHTML = `<div class="carrito-vacio"><h2 class="subtitulo">Venta actual</h2><p class="tenue">Toca un producto o escanea su código para agregarlo.</p></div>`;
    return;
  }
  const lineas = [...estado.carrito].map(([id, c]) => {
    const p = producto(id);
    return `<li class="linea">
      <div class="linea-nombre"><b>${esc(p.nombre_completo)}</b><span class="tenue">${dinero(p.precio)} c/u</span></div>
      <div class="cantidad">
        <button class="btn btn-chico" data-menos="${id}" aria-label="Quitar uno">−</button>
        <span aria-live="polite">${c}</span>
        <button class="btn btn-chico" data-mas="${id}" aria-label="Agregar uno">+</button>
      </div>
      <b class="linea-total">${dinero(p.precio * c)}</b>
    </li>`;
  }).join("");

  const efectivo = estado.metodo === "Efectivo";
  caja.innerHTML = `
    <div class="carrito-cabeza">
      <h2 class="subtitulo">Venta actual</h2>
      <button class="enlace" id="vaciar">Vaciar</button>
      <button class="cerrar-hoja" id="cerrar-hoja" aria-label="Cerrar">✕</button>
    </div>
    <ul class="lineas">${lineas}</ul>
    <div class="carrito-total"><span>Total</span><b class="precio">${dinero(t)}</b></div>
    <div class="metodos" role="radiogroup" aria-label="Método de pago">
      ${["Efectivo", "Deuna"].map((m) => `<button class="metodo ${estado.metodo === m ? "activo" : ""}" data-metodo="${m}" role="radio" aria-checked="${estado.metodo === m}">${m === "Efectivo" ? ICONO_EFECTIVO : ICONO_DEUNA}${m}</button>`).join("")}
    </div>
    ${efectivo ? `
      <label class="campo">Con cuánto paga
        <input id="recibido" inputmode="decimal" placeholder="${dinero(t)}" value="${esc(estado.recibido)}" autocomplete="off">
      </label>
      <div class="billetes">
        ${BILLETES.filter((b) => b > t).slice(0, 3).map((b) => `<button class="chip" data-billete="${b}">${dinero(b)}</button>`).join("")}
        <button class="chip" data-billete="${t}">Exacto</button>
      </div>
      <p class="vueltas" id="vueltas">${textoVueltas()}</p>` : `
      <p class="tenue nota-deuna">Muestra el QR de Deuna y confirma cuando veas el pago.</p>`}
    <button class="btn btn-rojo btn-ancho cobrar" id="cobrar" ${estado.cobrando ? "disabled" : ""}>
      ${estado.cobrando ? "Guardando…" : `Cobrar ${dinero(t)}`}
    </button>`;
}

function textoVueltas() {
  const r = aCentavos(estado.recibido), t = total();
  if (!estado.recibido) return "";
  if (r < t) return `<span class="falta">Faltan ${dinero(t - r)}</span>`;
  return `Vueltas: <b>${dinero(r - t)}</b>`;
}

function abrirHoja(abrir) {
  $("#carrito", raiz).classList.toggle("abierto", abrir);
  $("#velo", raiz).classList.toggle("visible", abrir);
  if (abrir) setTimeout(() => $("#recibido", raiz)?.focus({ preventScroll: true }), 300);
}

async function cobrar() {
  const t = total();
  const efectivo = estado.metodo === "Efectivo";
  const recibido = efectivo ? (aCentavos(estado.recibido) || t) : null;
  if (efectivo && recibido < t) { avisar(`Faltan ${dinero(t - recibido)}.`, "error"); return; }

  estado.cobrando = true;
  pintarCarrito();
  try {
    const venta = await api.post("/api/ventas", {
      items: [...estado.carrito].map(([producto_id, cantidad]) => ({ producto_id, cantidad })),
      metodo: estado.metodo,
      recibido,
    });
    estado.carrito.clear();
    estado.recibido = "";
    estado.metodo = "Efectivo";
    estado.buscar = "";
    const detalle = venta.vueltas ? `${dinero(venta.total)} · Vueltas ${dinero(venta.vueltas)}` : `${dinero(venta.total)} · ${venta.metodo}`;
    celebrar("Venta registrada", detalle, venta.vueltas ? 2600 : 1700);
    await mostrarVender(raiz);          // recarga el stock actualizado
    const bajos = estado.productos.filter((p) => venta.items.some((i) => i.producto_id === p.id) && p.stock_bajo);
    if (bajos.length) setTimeout(() => avisar(`Quedan pocos: ${bajos.map((p) => `${p.nombre} (${p.stock})`).join(", ")}`), 1800);
  } catch (e) {
    avisar(e.message, "error");
    if (e.estado === 400) await mostrarVender(raiz);   // por si el stock cambió
  } finally {
    estado.cobrando = false;
    if (raiz.isConnected) pintarCarrito();
  }
}

// ---------- Eventos ----------
function conectarEventos() {
  // los eventos van en el contenedor nuevo, así no se repiten al volver a pintar
  const caja = raiz.firstElementChild;
  const buscar = $("#buscar", raiz);
  buscar.addEventListener("input", () => { estado.buscar = buscar.value; pintarProductos(); });
  buscar.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const q = buscar.value.trim();
    if (!q) return;
    // Primero se busca como código de barras (así funcionan los lectores)
    let p = estado.productos.find((x) => x.codigo && x.codigo === q);
    if (!p) {
      const visibles = [...$("#productos", raiz).querySelectorAll(".producto:not(.agotado)")];
      if (visibles.length === 1) p = producto(Number(visibles[0].dataset.id));
    }
    if (p) {
      agregar(p.id, $(`.producto[data-id="${p.id}"]`, raiz));
      estado.buscar = ""; buscar.value = ""; pintarProductos();
    } else {
      avisar(`No hay ningún producto con “${q}”.`, "error");
    }
  });

  caja.addEventListener("click", (e) => {
    const cat = e.target.closest("[data-categoria]");
    if (cat) { estado.categoria = cat.dataset.categoria; pintarCategorias(); pintarProductos(); return; }

    const prod = e.target.closest(".producto");
    if (prod) { agregar(Number(prod.dataset.id), prod); return; }

    if (e.target.closest("#barra-carrito")) { abrirHoja(true); return; }
    if (e.target.closest("#velo") || e.target.closest("#cerrar-hoja")) { abrirHoja(false); return; }

    const mas = e.target.closest("[data-mas]");
    if (mas) { cambiar(Number(mas.dataset.mas), 1); return; }
    const menos = e.target.closest("[data-menos]");
    if (menos) { cambiar(Number(menos.dataset.menos), -1); return; }

    if (e.target.closest("#vaciar")) { estado.carrito.clear(); estado.recibido = ""; pintarProductos(); pintarCarrito(); return; }

    const metodo = e.target.closest("[data-metodo]");
    if (metodo) { estado.metodo = metodo.dataset.metodo; pintarCarrito(); return; }

    const billete = e.target.closest("[data-billete]");
    if (billete) { estado.recibido = (Number(billete.dataset.billete) / 100).toFixed(2).replace(".", ","); pintarCarrito(); return; }

    if (e.target.closest("#cobrar")) cobrar();
  });

  caja.addEventListener("input", (e) => {
    if (e.target.id === "recibido") {
      estado.recibido = e.target.value;
      $("#vueltas", raiz).innerHTML = textoVueltas();
    }
  });
  caja.addEventListener("keydown", (e) => {
    if (e.target.id === "recibido" && e.key === "Enter") { e.preventDefault(); cobrar(); }
    if (e.key === "Escape") abrirHoja(false);
  });
}
