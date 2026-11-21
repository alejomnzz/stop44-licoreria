// Pantalla de Ventas del día: lista de ventas, totales, anulaciones y el
// cierre de caja para mandar por WhatsApp.
// El administrador ve todo; el vendedor solo sus ventas y sin ganancias.

import { api } from "./api.js";
import { $, esc, dinero, fechaHoy, avisar, abrirModal, cerrarModal, confirmar, cargando, barraPagos } from "./ui.js";

let raiz = null, sesion = null;
let fecha = fechaHoy();

const sumarDias = (iso, n) => {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const nombreDia = (iso) => {
  if (iso === fechaHoy()) return "Hoy";
  if (iso === sumarDias(fechaHoy(), -1)) return "Ayer";
  const t = new Date(iso + "T12:00:00").toLocaleDateString("es-EC", { weekday: "long", day: "numeric", month: "long" });
  return t.charAt(0).toUpperCase() + t.slice(1);
};

export async function mostrarVentas(el, usuario) {
  raiz = el; sesion = usuario;
  const admin = sesion.rol === "admin";
  el.innerHTML = cargando();
  let ventas, resumen = null;
  try {
    [ventas, resumen] = await Promise.all([
      api.get(`/api/ventas?fecha=${fecha}`),
      admin ? api.get(`/api/resumen?desde=${fecha}`) : Promise.resolve(null),
    ]);
  } catch (e) {
    el.innerHTML = `<div class="panel-roto vacio"><p>${esc(e.message)}</p></div>`;
    return;
  }

  const validas = ventas.filter((v) => !v.anulada);
  const total = validas.reduce((s, v) => s + v.total, 0);
  const porMetodo = {};
  validas.forEach((v) => { porMetodo[v.metodo] = (porMetodo[v.metodo] || 0) + v.total; });
  const efectivo = porMetodo.Efectivo || 0;
  const abonosEfectivo = resumen?.abonos?.Efectivo || 0;          // pagos de fiados (solo lo ve el admin)
  const abonosTotal = Object.values(resumen?.abonos || {}).reduce((a, b) => a + b, 0);

  el.innerHTML = `<div class="pantalla-ventas">
    <div class="encabezado">
      <h1 class="titulo">${admin ? "Ventas" : "Mis ventas"}</h1>
      ${admin ? `<div class="botones-encabezado">
        <a class="btn" href="/api/reporte" download><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M4 19h16"/></svg> Excel</a>
        ${validas.length ? '<button class="btn btn-rojo" id="cierre">Cierre del día</button>' : ""}
      </div>` : ""}
    </div>

    <div class="selector-dia">
      <button class="btn btn-chico" id="dia-antes" aria-label="Día anterior">‹</button>
      <label class="dia-actual">
        <b>${esc(nombreDia(fecha))}</b>
        <input type="date" id="dia" value="${fecha}" max="${fechaHoy()}" aria-label="Elegir fecha">
      </label>
      <button class="btn btn-chico" id="dia-despues" aria-label="Día siguiente" ${fecha >= fechaHoy() ? "disabled" : ""}>›</button>
      ${fecha !== fechaHoy() ? '<button class="enlace" id="dia-hoy">Ir a hoy</button>' : ""}
    </div>

    <div class="cifras">
      <div class="cifra grande"><small>Vendido</small><b>${dinero(total)}</b></div>
      <div class="cifra"><small>Ventas</small><b>${validas.length}</b></div>
      ${admin ? `
        <div class="cifra"><small>Ganancia</small><b class="ganancia">${dinero(resumen.ganancia)}</b></div>
        <div class="cifra"><small>Venta promedio</small><b>${dinero(resumen.promedio)}</b></div>` : ""}
    </div>

    ${total ? `
    <section class="sticker caja">
      <h2 class="subtitulo">Cómo pagaron</h2>
      ${barraPagos(porMetodo)}
      ${abonosTotal ? `<p class="abonos-dia">Además se cobraron <b>${dinero(abonosTotal)}</b> de fiados (${Object.entries(resumen.abonos).map(([m, t]) => `${m.toLowerCase()} ${dinero(t)}`).join(", ")}).</p>` : ""}
      <p class="en-caja">Debe haber en la caja <b>${dinero(efectivo + abonosEfectivo)}</b> en efectivo${abonosEfectivo ? " (ventas + abonos)" : ""}${fecha === fechaHoy() ? " de hoy" : ""}.</p>
    </section>` : abonosTotal ? `
    <section class="sticker caja"><p class="abonos-dia">Se cobraron <b>${dinero(abonosTotal)}</b> de fiados. En la caja debe haber <b>${dinero(abonosEfectivo)}</b> en efectivo.</p></section>` : ""}

    ${admin && resumen.productos.length ? `
    <div class="dos-columnas">
      <section class="sticker">
        <h2 class="subtitulo">Lo más vendido</h2>
        <ol class="top">${resumen.productos.slice(0, 6).map((p) => `
          <li><span>${esc(p.nombre)}</span><span class="tenue">× ${p.cantidad}</span><b>${dinero(p.total)}</b></li>`).join("")}</ol>
      </section>
      ${Object.keys(resumen.por_vendedor).length > 1 ? `
      <section class="sticker">
        <h2 class="subtitulo">Por vendedor</h2>
        <ol class="top">${Object.entries(resumen.por_vendedor).map(([n, t]) => `<li><span>${esc(n)}</span><span></span><b>${dinero(t)}</b></li>`).join("")}</ol>
      </section>` : ""}
    </div>` : ""}

    <h2 class="subtitulo lista-titulo">${ventas.length ? `${ventas.length} ${ventas.length === 1 ? "venta" : "ventas"}` : ""}</h2>
    <div class="lista-ventas">
      ${ventas.length ? ventas.map((v) => tarjetaVenta(v, admin)).join("") : `
        <div class="panel-roto vacio"><p>${fecha === fechaHoy() ? "Todavía no hay ventas hoy. Cuando vendas, aparecen aquí." : "Ese día no hubo ventas."}</p>
        ${fecha === fechaHoy() ? '<a class="btn btn-rojo" href="#vender">Ir a vender</a>' : ""}</div>`}
    </div>
  </div>`;
  conectar(ventas);
}

function tarjetaVenta(v, admin) {
  const resumenItems = v.items.map((i) => `${i.cantidad}× ${esc(i.nombre)}`).join(", ");
  return `
    <article class="venta ${v.anulada ? "anulada" : ""}" data-venta="${v.id}">
      <button class="venta-cabeza" aria-expanded="false">
        <span class="venta-hora">${esc(v.hora)}</span>
        <span class="venta-items">${resumenItems}</span>
        <span class="venta-total">${v.anulada ? '<span class="etiqueta roja">Anulada</span>' : v.metodo === "Fiado" ? '<span class="etiqueta dorada">Fiado</span>' : ""}<b class="precio">${dinero(v.total)}</b></span>
      </button>
      <div class="venta-detalle" hidden>
        <ul>${v.items.map((i) => `<li><span>${i.cantidad} × ${esc(i.nombre)}</span><span class="tenue">${dinero(i.precio)} c/u</span><b>${dinero(i.precio * i.cantidad)}</b></li>`).join("")}</ul>
        <p class="tenue">
          ${v.metodo === "Efectivo" ? `Efectivo · pagó ${dinero(v.recibido)} · vueltas ${dinero(v.vueltas)}` : v.metodo === "Fiado" ? `Fiado a ${esc(v.cliente)}` : "Deuna"}
          ${v.vendedor ? ` · vendió ${esc(v.vendedor)}` : ""}
          ${admin && !v.anulada ? ` · ganancia ${dinero(v.ganancia)}` : ""}
        </p>
        ${admin && !v.anulada ? `<button class="btn btn-chico anular" data-anular="${v.id}">Anular venta</button>` : ""}
      </div>
    </article>`;
}

async function cierre() {
  const m = abrirModal(`<h2>Cierre del día</h2>${cargando()}`);
  try {
    const { texto } = await api.get(`/api/cierre?fecha=${fecha}`);
    m.innerHTML = `
      <h2>Cierre del día</h2>
      <pre class="cierre-texto">${esc(texto)}</pre>
      <div class="acciones">
        <button class="btn" id="copiar">Copiar</button>
        <a class="btn btn-rojo" id="whatsapp" href="https://wa.me/?text=${encodeURIComponent(texto)}" target="_blank" rel="noopener">Enviar por WhatsApp</a>
      </div>`;
    $("#copiar", m).onclick = async () => {
      try { await navigator.clipboard.writeText(texto); avisar("Cierre copiado"); cerrarModal(); }
      catch { avisar("No se pudo copiar. Selecciona el texto y cópialo.", "error"); }
    };
  } catch (e) { avisar(e.message, "error"); cerrarModal(); }
}

function conectar(ventas) {
  const caja = raiz.firstElementChild;
  const ir = (nueva) => { fecha = nueva > fechaHoy() ? fechaHoy() : nueva; mostrarVentas(raiz, sesion); };
  $("#dia-antes", caja).onclick = () => ir(sumarDias(fecha, -1));
  $("#dia-despues", caja).onclick = () => ir(sumarDias(fecha, 1));
  $("#dia-hoy", caja)?.addEventListener("click", () => ir(fechaHoy()));
  $("#dia", caja).addEventListener("change", (e) => { if (e.target.value) ir(e.target.value); });
  $("#cierre", caja)?.addEventListener("click", cierre);

  caja.addEventListener("click", async (e) => {
    const cabeza = e.target.closest(".venta-cabeza");
    if (cabeza) {
      const detalle = cabeza.nextElementSibling;
      detalle.hidden = !detalle.hidden;
      cabeza.setAttribute("aria-expanded", String(!detalle.hidden));
      cabeza.parentElement.classList.toggle("abierta", !detalle.hidden);
      return;
    }
    const anular = e.target.closest("[data-anular]");
    if (anular) {
      const v = ventas.find((x) => x.id === Number(anular.dataset.anular));
      const ok = await confirmar("¿Anular esta venta?",
        `${v.hora} · ${dinero(v.total)}. Los productos vuelven al inventario y la venta queda marcada como anulada.`, "Sí, anular");
      if (!ok) return;
      try { await api.post(`/api/ventas/${v.id}/anular`); avisar("Venta anulada. Los productos volvieron al inventario."); mostrarVentas(raiz, sesion); }
      catch (err) { avisar(err.message, "error"); }
    }
  });
}
