// Pantalla de Resumen (solo administrador): cómo va el negocio en los últimos
// 7 días, 30 días o el mes, comparado con el periodo anterior.

import { api } from "./api.js";
import { $, esc, dinero, cargando } from "./ui.js";

const PERIODOS = { semana: "Últimos 7 días", mes: "Este mes", treinta: "Últimos 30 días" };
let periodo = "semana";
let raiz = null;

const sumarDias = (iso, n) => {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const diasEntre = (a, b) => Math.round((new Date(b + "T12:00:00") - new Date(a + "T12:00:00")) / 86400000);
const diaCorto = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("es-EC", { weekday: "short", day: "numeric" });
const diaLargo = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("es-EC", { weekday: "long", day: "numeric", month: "long" });
const hora12 = (h) => `${h % 12 || 12} ${h < 12 ? "a. m." : "p. m."}`;

function rango(hoy) {
  const hasta = hoy;
  const desde = periodo === "semana" ? sumarDias(hoy, -6) : periodo === "treinta" ? sumarDias(hoy, -29) : hoy.slice(0, 8) + "01";
  const largo = diasEntre(desde, hasta) + 1;
  return { desde, hasta, antesDesde: sumarDias(desde, -largo), antesHasta: sumarDias(desde, -1) };
}

function variacion(actual, antes) {
  if (!antes) return "";
  const pct = Math.round(((actual - antes) / antes) * 100);
  const sube = pct >= 0;
  return `<span class="variacion ${sube ? "sube" : "baja"}" title="Comparado con el periodo anterior">${sube ? "▲" : "▼"} ${Math.abs(pct)}%</span>`;
}

export async function mostrarResumen(el) {
  raiz = el;
  el.innerHTML = cargando();
  let datos;
  try {
    const { hoy } = await api.get("/api/hoy");
    const r = rango(hoy);
    const [actual, antes, dias, horas, bajos] = await Promise.all([
      api.get(`/api/resumen?desde=${r.desde}&hasta=${r.hasta}`),
      api.get(`/api/resumen?desde=${r.antesDesde}&hasta=${r.antesHasta}`),
      api.get(`/api/resumen/dias?desde=${r.desde}&hasta=${r.hasta}`),
      api.get(`/api/resumen/horas?desde=${r.desde}&hasta=${r.hasta}`),
      api.get("/api/stock-bajo"),
    ]);
    datos = { hoy, actual, antes, dias, horas, bajos };
  } catch (e) {
    el.innerHTML = `<div class="panel-roto vacio"><p>${esc(e.message)}</p></div>`;
    return;
  }
  const { hoy, actual, antes, dias, horas, bajos } = datos;
  const efectivo = actual.por_metodo.Efectivo || 0, deuna = actual.por_metodo.Deuna || 0;
  const masVendidos = [...actual.productos].sort((a, b) => b.total - a.total).slice(0, 10);   // por plata que dejaron
  const maxProducto = Math.max(1, ...masVendidos.map((p) => p.total));

  el.innerHTML = `<div class="pantalla-resumen">
    <div class="encabezado">
      <h1 class="titulo">Resumen</h1>
      <a class="btn" href="/api/reporte" download><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M4 19h16"/></svg> Descargar Excel</a>
    </div>
    <div class="categorias periodos" role="tablist">
      ${Object.entries(PERIODOS).map(([id, nombre]) => `<button class="chip ${id === periodo ? "activo" : ""}" data-periodo="${id}" role="tab" aria-selected="${id === periodo}">${nombre}</button>`).join("")}
    </div>

    <div class="cifras">
      <div class="cifra grande"><small>Vendido</small><b>${dinero(actual.total)}</b>${variacion(actual.total, antes.total)}</div>
      <div class="cifra"><small>Ganancia</small><b class="ganancia">${dinero(actual.ganancia)}</b>${variacion(actual.ganancia, antes.ganancia)}</div>
      <div class="cifra"><small>Ventas</small><b>${actual.num_ventas}</b>${variacion(actual.num_ventas, antes.num_ventas)}</div>
      <div class="cifra"><small>Venta promedio</small><b>${dinero(actual.promedio)}</b></div>
    </div>
    <p class="tenue comparacion">Las flechas comparan con los ${diasEntre(rango(hoy).desde, hoy) + 1} días anteriores.</p>

    <section class="sticker grafica-caja">
      <h2 class="subtitulo">Ventas por día</h2>
      ${actual.total ? `<div class="grafica" id="g-dias"></div>` : '<p class="tenue">No hay ventas en este periodo.</p>'}
    </section>

    ${actual.total ? `
    <div class="dos-columnas">
      <section class="sticker grafica-caja">
        <h2 class="subtitulo">A qué hora se vende más</h2>
        <p class="tenue" id="mejor-hora"></p>
        <div class="grafica" id="g-horas"></div>
      </section>
      <section class="sticker">
        <h2 class="subtitulo">Cómo pagaron</h2>
        <div class="barra-pagos" role="img" aria-label="Efectivo ${dinero(efectivo)}, Deuna ${dinero(deuna)}">
          <span class="pago-efectivo" style="flex:${efectivo || 0.0001}"></span><span class="pago-deuna" style="flex:${deuna || 0.0001}"></span>
        </div>
        <div class="pagos-detalle">
          <div><i class="punto efectivo"></i>Efectivo <b>${dinero(efectivo)}</b> <span class="tenue">${Math.round((efectivo / actual.total) * 100)}%</span></div>
          <div><i class="punto deuna"></i>Deuna <b>${dinero(deuna)}</b> <span class="tenue">${Math.round((deuna / actual.total) * 100)}%</span></div>
        </div>
        ${Object.keys(actual.por_vendedor).length ? `
          <h2 class="subtitulo" style="margin-top:20px">Por vendedor</h2>
          <ol class="top">${Object.entries(actual.por_vendedor).map(([n, t]) => `<li><span>${esc(n)}</span><span></span><b>${dinero(t)}</b></li>`).join("")}</ol>` : ""}
      </section>
    </div>

    <section class="sticker">
      <h2 class="subtitulo">Los más vendidos</h2>
      <ol class="ranking">${masVendidos.map((p) => `
        <li>
          <span class="ranking-nombre">${esc(p.nombre)} <span class="tenue">× ${p.cantidad}</span></span>
          <span class="ranking-barra"><i style="width:${Math.max(2, (p.total / maxProducto) * 100)}%"></i></span>
          <b>${dinero(p.total)}</b>
        </li>`).join("")}
      </ol>
    </section>` : ""}

    <section class="sticker">
      <h2 class="subtitulo">Por pedir</h2>
      ${bajos.length ? `<ul class="por-pedir">${bajos.map((p) => `
        <li><span>${esc(p.nombre_completo)}</span><span class="etiqueta ${p.stock <= 0 ? "roja" : "ambar"}">${p.stock <= 0 ? "Agotado" : `Quedan ${p.stock}`}</span></li>`).join("")}</ul>
        <a class="btn btn-chico" href="#inventario">Ir a Inventario</a>`
      : '<p class="tenue">Todo está por encima del mínimo.</p>'}
    </section>
  </div>`;

  if (actual.total) {
    const listaDias = Object.entries(dias);
    graficaBarras($("#g-dias", el), listaDias.map(([f, t]) => ({
      valor: t,
      etiqueta: listaDias.length <= 8 ? diaCorto(f) : (Number(f.slice(8)) % 5 === 1 ? f.slice(8).replace(/^0/, "") : ""),
      detalle: `${diaLargo(f)}`,
      resalta: f === hoy,
    })), "Ventas por día");

    // horas: solo desde la primera hasta la última hora con ventas, para que no sobre espacio
    const conVentas = Object.entries(horas).filter(([, t]) => t > 0).map(([h]) => Number(h));
    const desde = Math.min(...conVentas), hasta = Math.max(...conVentas);
    const tramo = Object.entries(horas).map(([h, t]) => [Number(h), t]).filter(([h]) => h >= desde && h <= hasta);
    graficaBarras($("#g-horas", el), tramo.map(([h, t]) => ({
      valor: t, etiqueta: tramo.length <= 8 || h % 3 === 0 ? hora12(h).replace(" a. m.", "a").replace(" p. m.", "p") : "",
      detalle: `De ${hora12(h)} a ${hora12((h + 1) % 24)}`,
    })), "Ventas por hora", 150);
    const mejor = tramo.reduce((a, b) => (b[1] > a[1] ? b : a));
    $("#mejor-hora", el).textContent = `La hora más fuerte: de ${hora12(mejor[0])} a ${hora12((mejor[0] + 1) % 24)}`;
  }

  el.querySelectorAll("[data-periodo]").forEach((b) => b.addEventListener("click", () => { periodo = b.dataset.periodo; mostrarResumen(raiz); }));
}

// Gráfica de barras en SVG: barras finas con punta redondeada, una sola etiqueta
// de valor (el máximo) y un recuadro con el detalle al pasar el dedo o el mouse.
function graficaBarras(caja, puntos, titulo, alto = 190) {
  // se dibuja al ancho real de la pantalla, así las letras quedan de su tamaño en celular y en PC
  const ancho = Math.max(260, Math.round(caja.clientWidth || 640)), abajo = 26, arriba = 22;
  const max = Math.max(1, ...puntos.map((p) => p.valor));
  const paso = ancho / puntos.length;
  const grosor = Math.min(38, Math.max(4, paso - 2));        // 2 px de separación entre barras
  const y = (v) => arriba + (alto - arriba - abajo) * (1 - v / max);
  const iMax = puntos.findIndex((p) => p.valor === max);

  const barras = puntos.map((p, i) => {
    const x = i * paso + (paso - grosor) / 2;
    const top = y(p.valor), base = alto - abajo, r = Math.min(4, grosor / 2, base - top);
    const d = p.valor > 0
      ? `M${x},${base} V${top + r} Q${x},${top} ${x + r},${top} H${x + grosor - r} Q${x + grosor},${top} ${x + grosor},${top + r} V${base} Z`
      : "";
    return `<g class="barra ${p.resalta ? "hoy" : ""}" data-i="${i}" style="--retraso:${i * 25}ms">
        <rect class="zona" x="${i * paso}" y="0" width="${paso}" height="${alto}"/>
        ${d ? `<path d="${d}"/>` : ""}
        ${p.etiqueta ? `<text x="${x + grosor / 2}" y="${alto - 8}" text-anchor="middle" class="eje">${esc(p.etiqueta)}</text>` : ""}
        ${i === iMax ? `<text x="${x + grosor / 2}" y="${top - 6}" text-anchor="middle" class="valor-max">${dinero(p.valor)}</text>` : ""}
      </g>`;
  }).join("");

  caja.innerHTML = `
    <svg viewBox="0 0 ${ancho} ${alto}" width="${ancho}" height="${alto}" role="img" aria-label="${esc(titulo)}. Máximo ${dinero(max)}.">
      <line x1="0" x2="${ancho}" y1="${alto - abajo}" y2="${alto - abajo}" class="base"/>
      ${barras}
    </svg>
    <div class="globo" hidden></div>
    <table class="solo-lectores"><caption>${esc(titulo)}</caption>
      ${puntos.map((p) => `<tr><th>${esc(p.detalle)}</th><td>${dinero(p.valor)}</td></tr>`).join("")}</table>`;

  const globo = caja.querySelector(".globo");
  const mostrar = (g) => {
    caja.querySelectorAll(".barra.activa").forEach((b) => b.classList.remove("activa"));
    if (!g) { globo.hidden = true; return; }
    g.classList.add("activa");
    const p = puntos[Number(g.dataset.i)];
    globo.innerHTML = `<small>${esc(p.detalle)}</small><b>${dinero(p.valor)}</b>`;
    globo.hidden = false;
    const r = g.getBoundingClientRect(), c = caja.getBoundingClientRect();
    const izquierda = Math.min(Math.max(r.left - c.left + r.width / 2 - globo.offsetWidth / 2, 0), c.width - globo.offsetWidth);
    globo.style.left = `${izquierda}px`;
  };
  caja.addEventListener("pointermove", (e) => mostrar(e.target.closest(".barra")));
  caja.addEventListener("pointerdown", (e) => mostrar(e.target.closest(".barra")));
  caja.addEventListener("pointerleave", () => mostrar(null));
}
