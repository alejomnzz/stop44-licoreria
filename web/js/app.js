// Arranque de la app: revisa la sesión, arma la navegación y muestra cada
// pantalla según la dirección (#vender, #inventario, ...).

import { api, ErrorApi } from "./api.js";
import { $, esc, dinero, avisar, confirmar, celebrar, cargando } from "./ui.js";
import { dibujoProducto } from "./dibujos.js";
import { mostrarAcceso } from "./acceso.js";
import { mostrarVender } from "./vender.js";
import { mostrarInventario } from "./inventario.js";
import { mostrarVentas } from "./ventas.js";
import { mostrarResumen } from "./resumen.js";
import { mostrarFiados } from "./fiados.js";
import { mostrarUsuarios, cambiarMiClave, actualizarAviso } from "./usuarios.js";

// ---------- Íconos (trazos simples, heredan el color) ----------
const ICONO = {
  vender: '<path d="M3 4h2l2.4 11h11.2L21 7H6.2"/><circle cx="9" cy="19.5" r="1.5"/><circle cx="17" cy="19.5" r="1.5"/>',
  inventario: '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/>',
  ventas: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
  fiados: '<path d="M4 4h11a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3z"/><path d="M18 20a2 2 0 0 0 2-2V8"/><path d="M8 9h6M8 13h4"/>',
  resumen: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  usuarios: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c1.9.7 3.1 2.3 3.5 5.2"/>',
};
const icono = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONO[n]}</svg>`;

// ---------- Pantallas ----------
// Cada pantalla es una función que recibe el contenedor y la sesión.
export const PANTALLAS = {
  vender:     { nombre: "Vender",     soloAdmin: false, mostrar: mostrarVender },
  inventario: { nombre: "Inventario", soloAdmin: true,  mostrar: mostrarInventario },
  ventas:     { nombre: "Ventas",     soloAdmin: false, mostrar: mostrarVentas },
  fiados:     { nombre: "Fiados",     soloAdmin: false, mostrar: mostrarFiados },
  resumen:    { nombre: "Resumen",    soloAdmin: true,  mostrar: mostrarResumen },
  usuarios:   { nombre: "Usuarios",   soloAdmin: true,  mostrar: mostrarUsuarios },
};

// Muestrario: todas las piezas del diseño en un solo lugar, para revisarlas
function muestrario(el) {
  const categorias = ["Aguardiente", "Ron", "Whisky", "Cerveza", "Vino", "Gaseosas y aguas", "Energizantes", "Hielo"];
  el.innerHTML = `
    <h1 class="titulo">Muestrario</h1>
    <div class="rejilla">
      <section class="sticker">
        <h2 class="subtitulo">Botones</h2>
        <div style="display:flex;flex-wrap:wrap;gap:10px">
          <button class="btn btn-rojo" data-prueba="celebrar">Cobrar</button>
          <button class="btn" data-prueba="aviso">Aviso</button>
          <button class="btn" data-prueba="error">Error</button>
          <button class="btn btn-chico" data-prueba="ventana">Ventana</button>
        </div>
      </section>
      <section class="sticker">
        <h2 class="subtitulo">Etiquetas</h2>
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <span class="chip activo">Todo</span><span class="chip">Aguardiente</span><span class="chip">Cerveza</span>
          <span class="etiqueta">18</span><span class="etiqueta roja">Quedan 3</span>
          <span class="etiqueta verde">Activo</span><span class="etiqueta ambar">Pendiente</span>
        </div>
      </section>
      <form class="panel-roto" style="display:flex;flex-direction:column;gap:12px" onsubmit="return false">
        <label class="campo">Usuario<input placeholder="laura" autocomplete="off"></label>
        <label class="campo">Precio de venta<input inputmode="numeric" placeholder="$12,50"><span class="error">El precio debe ser mayor que cero.</span></label>
        <button class="btn btn-rojo btn-ancho">Guardar</button>
      </form>
    </div>
    <h2 class="subtitulo" style="margin-top:22px">Dibujos de productos por categoría</h2>
    <div class="rejilla" style="grid-template-columns:repeat(auto-fill,minmax(150px,1fr))">
      ${categorias.map((c) => `
        <div class="sticker" style="display:flex;flex-direction:column;gap:2px">
          <div class="dibujo">${dibujoProducto(c)}</div>
          <b>${esc(c)}</b><span class="precio" style="font-size:19px">${dinero(1250)}</span>
        </div>`).join("")}
    </div>`;
  el.querySelectorAll("[data-prueba]").forEach((b) => b.addEventListener("click", async () => {
    const p = b.dataset.prueba;
    if (p === "celebrar") celebrar("Venta registrada", `${dinero(1675)} · Efectivo`);
    if (p === "aviso") avisar("Producto guardado");
    if (p === "error") avisar("Solo hay 3 de Aguardiente Antioqueño.", "error");
    if (p === "ventana") {
      const si = await confirmar("¿Anular esta venta?", "Los productos vuelven al inventario.", "Sí, anular");
      avisar(si ? "Venta anulada" : "No se anuló nada");
    }
  }));
}

// ---------- Sesión y navegación ----------
let sesion = null;

function pintarCabecera() {
  $("#quien").innerHTML = sesion
    ? `<button class="mi-cuenta" id="mi-cuenta" title="Cambiar mi contraseña"><span class="nombre">${esc(sesion.nombre)}</span><span class="rol">${sesion.rol === "admin" ? "Administrador" : "Vendedor"}</span></button>
       <button class="btn btn-chico" id="salir" style="border-color:#fff">Salir</button>`
    : "";
  $("#mi-cuenta")?.addEventListener("click", cambiarMiClave);
  $("#salir")?.addEventListener("click", async () => {
    await api.post("/api/auth/salir");
    sesion = null;
    iniciar();
  });
}

function pintarNav(actual) {
  const visibles = Object.entries(PANTALLAS).filter(([, p]) => !p.soloAdmin || sesion?.rol === "admin");
  $("#nav").innerHTML = visibles.map(([id, p]) =>
    `<a href="#${id}" class="${id === actual ? "activo" : ""}" ${id === actual ? 'aria-current="page"' : ""}>${icono(id)}<span>${p.nombre}</span></a>`).join("");
}

function sinSesion() {
  document.body.classList.add("sin-sesion");
  $("#nav").innerHTML = "";
  mostrarAcceso($("#contenido"), (usuario, esNueva) => {
    sesion = usuario;
    document.body.classList.remove("sin-sesion");
    pintarCabecera();
    if (!location.hash || location.hash === "#muestrario") location.hash = "#vender";
    mostrar();
    celebrar(esNueva ? "Cuenta creada" : `Hola, ${usuario.nombre.split(" ")[0]}`,
             esNueva ? "Ya eres el administrador de Stop 44" : "", 1300);
  });
}

function mostrar() {
  const id = location.hash.slice(1) || "vender";
  const el = $("#contenido");
  if (id === "muestrario") { pintarNav(null); return muestrario(el); }
  const pantalla = PANTALLAS[id];
  if (!pantalla || (pantalla.soloAdmin && sesion.rol !== "admin")) { location.hash = "#vender"; return; }
  pintarNav(id);
  if (sesion.rol === "admin") actualizarAviso();
  pantalla.mostrar(el, sesion);
  window.scrollTo(0, 0);
}

async function iniciar() {
  $("#contenido").innerHTML = cargando();
  try {
    sesion = await api.get("/api/auth/yo");
  } catch (e) {
    sesion = null;
    if (!(e instanceof ErrorApi) || e.estado !== 401) avisar(e.message, "error");
  }
  pintarCabecera();
  if (sesion) { document.body.classList.remove("sin-sesion"); mostrar(); } else sinSesion();
}

window.addEventListener("hashchange", () => { if (sesion) mostrar(); });
iniciar();

// ---------- Instalar como app ----------
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

// Android y computador: el navegador ofrece instalar; mostramos nuestro propio botón
let pedidoInstalar = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  pedidoInstalar = e;
  $("#instalar").hidden = false;
});
$("#instalar").addEventListener("click", async () => {
  if (!pedidoInstalar) return;
  pedidoInstalar.prompt();
  const { outcome } = await pedidoInstalar.userChoice;
  if (outcome === "accepted") $("#instalar").hidden = true;
  pedidoInstalar = null;
});
window.addEventListener("appinstalled", () => { $("#instalar").hidden = true; celebrar("App instalada", "Búscala en tu pantalla de inicio", 1800); });

// iPhone: Safari no tiene botón de instalar, así que se explica una sola vez
const esIphone = /iphone|ipad|ipod/i.test(navigator.userAgent);
const yaInstalada = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
if (esIphone && !yaInstalada) {
  let visto = false;
  try { visto = localStorage.getItem("stop44_aviso_iphone") === "1"; } catch { /* modo privado */ }
  if (!visto) {
    setTimeout(() => avisar("Para instalarla: toca Compartir y luego \"Agregar a inicio\"."), 3000);
    try { localStorage.setItem("stop44_aviso_iphone", "1"); } catch { /* sin almacenamiento */ }
  }
}

