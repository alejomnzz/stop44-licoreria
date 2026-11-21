// Piezas de interfaz reutilizables: formato de pesos, avisos, ventanas y la
// confirmación grande con la mano de "pare".

// El dinero llega de la API en centavos: 1250 -> "$12,50"
export const dinero = (centavos) => {
  const n = Math.round(centavos || 0), signo = n < 0 ? "-" : "";
  const dolares = Math.floor(Math.abs(n) / 100), cents = Math.abs(n) % 100;
  return `${signo}$${dolares.toLocaleString("es-EC").replace(/,/g, ".")},${String(cents).padStart(2, "0")}`;
};

// Lo que escribe el usuario a centavos: "12,50" o "12.50" -> 1250
export const aCentavos = (texto) => {
  let t = String(texto ?? "").replace(/[^\d,.]/g, "");
  if (!t) return 0;
  if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
  else if (!(t.split(".").length === 2 && t.split(".")[1].length <= 2)) t = t.replace(/\./g, "");
  return Math.round(parseFloat(t) * 100) || 0;
};

export const fechaHoy = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const fechaLarga = (iso) =>
  new Date(iso + "T12:00:00").toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long" });

// Escapa texto para meterlo en HTML sin riesgo (nombres de productos, etc.)
export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export const $ = (sel, raiz = document) => raiz.querySelector(sel);

// ---------- Avisos cortos ----------
export function avisar(texto, tipo = "") {
  const caja = $("#avisos");
  const el = document.createElement("div");
  el.className = `aviso ${tipo}`;
  el.setAttribute("role", tipo === "error" ? "alert" : "status");
  el.textContent = texto;
  caja.appendChild(el);
  setTimeout(() => { el.classList.add("sale"); setTimeout(() => el.remove(), 260); }, tipo === "error" ? 4200 : 2600);
}

// ---------- Ventanas ----------
export function abrirModal(html, { alAbrir } = {}) {
  cerrarModal();
  const fondo = document.createElement("div");
  fondo.className = "fondo-modal";
  fondo.id = "modal";
  fondo.innerHTML = `<div class="modal" role="dialog" aria-modal="true">${html}</div>`;
  fondo.addEventListener("click", (e) => { if (e.target === fondo || e.target.closest("[data-cerrar]")) cerrarModal(); });
  document.body.appendChild(fondo);
  const primero = fondo.querySelector("input, select, textarea, button");
  primero?.focus();
  alAbrir?.(fondo.querySelector(".modal"));
  return fondo.querySelector(".modal");
}

export function cerrarModal() {
  $("#modal")?.remove();
}

export function confirmar(titulo, texto, textoBoton = "Confirmar") {
  return new Promise((resolver) => {
    const m = abrirModal(`
      <h2>${esc(titulo)}</h2>
      <p>${esc(texto)}</p>
      <div class="acciones">
        <button class="btn" data-cerrar>Cancelar</button>
        <button class="btn btn-rojo" data-si>${esc(textoBoton)}</button>
      </div>`);
    m.querySelector("[data-si]").onclick = () => { cerrarModal(); resolver(true); };
    m.closest(".fondo-modal").addEventListener("click", (e) => {
      if (e.target.matches(".fondo-modal") || e.target.closest("[data-cerrar]")) resolver(false);
    });
  });
}

// ---------- La mano de "pare" ----------
export const MANO = `<svg viewBox="0 0 70 80" aria-hidden="true"><path d="M16 44V22a5 5 0 0 1 10 0v14V12a5 5 0 0 1 10 0v24V9a5 5 0 0 1 10 0v27V16a5 5 0 0 1 10 0v34c0 16-10 26-24 26-10 0-16-5-22-14L4 44a5 5 0 0 1 8-6z" fill="#fff" stroke="#000" stroke-width="3" stroke-linejoin="round"/></svg>`;

export function celebrar(titulo, detalle = "", duracion = 1700) {
  const el = document.createElement("div");
  el.className = "celebra";
  el.setAttribute("role", "status");
  el.innerHTML = `<div><div class="octagono"><div>${MANO}</div></div><h3>${esc(titulo)}</h3><p>${esc(detalle)}</p></div>`;
  document.body.appendChild(el);
  const quitar = () => { el.classList.add("sale"); setTimeout(() => el.remove(), 260); };
  el.addEventListener("click", quitar);
  setTimeout(quitar, duracion);
}

export const cargando = () => `<div class="cargando" aria-label="Cargando"><div class="octagono"><div></div></div></div>`;
