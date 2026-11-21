// Pantalla de Fiados: clientes que deben, sus cuentas, abonos y recordatorio por WhatsApp.
// La pueden usar todos; anular abonos y quitar clientes es solo del administrador.

import { api } from "./api.js";
import { $, esc, dinero, aCentavos, avisar, abrirModal, cerrarModal, confirmar, celebrar, cargando } from "./ui.js";

let raiz = null, sesion = null;
let buscar = "";

const iniciales = (n) => n.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
const sinTildes = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const cuando = (m) => {
  if (!m) return "Sin movimientos";
  const [f, h] = m.split(" ");
  const d = new Date(f + "T12:00:00");
  return `Último movimiento: ${d.toLocaleDateString("es-EC", { day: "numeric", month: "short" })} ${h || ""}`;
};

// Número de Ecuador para WhatsApp: 0991234567 -> 593991234567
export function numeroWhatsApp(telefono) {
  const t = String(telefono || "").replace(/[^\d]/g, "");
  if (t.startsWith("593")) return t;
  if (t.length === 10 && t.startsWith("0")) return "593" + t.slice(1);
  if (t.length === 9 && t.startsWith("9")) return "593" + t;
  return t;
}

function enlaceWhatsApp(c) {
  const texto = `Hola ${c.nombre.split(" ")[0]}, te saludamos de Stop 44. Tu saldo pendiente es de ${dinero(c.saldo)}. ¡Gracias por tu preferencia!`;
  const numero = numeroWhatsApp(c.telefono);
  return `https://wa.me/${numero}?text=${encodeURIComponent(texto)}`;
}

export async function mostrarFiados(el, usuario) {
  raiz = el; sesion = usuario;
  el.innerHTML = cargando();
  let datos;
  try { datos = await api.get("/api/clientes"); }
  catch (e) { el.innerHTML = `<div class="panel-roto vacio"><p>${esc(e.message)}</p></div>`; return; }

  const deben = datos.clientes.filter((c) => c.saldo > 0);
  el.innerHTML = `<div class="pantalla-fiados">
    <div class="encabezado">
      <h1 class="titulo">Fiados</h1>
      <button class="btn btn-rojo" id="nuevo-cliente">+ Cliente</button>
    </div>
    <div class="cifras">
      <div class="cifra grande alerta-suave"><small>Te deben en total</small><b>${dinero(datos.por_cobrar)}</b></div>
      <div class="cifra"><small>Clientes que deben</small><b>${deben.length}</b></div>
    </div>
    ${datos.clientes.length ? `
    <label class="buscador">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>
      <input id="buscar-cliente" type="search" placeholder="Buscar cliente" autocomplete="off" value="${esc(buscar)}" aria-label="Buscar cliente">
    </label>
    <div class="lista-clientes" id="lista-clientes"></div>` : `
    <div class="panel-roto vacio">
      <p>Aquí aparecen los clientes que llevan fiado. Agrégalos aquí o directamente al vender, eligiendo <b>Fiado</b> como forma de pago.</p>
      <button class="btn btn-rojo" data-nuevo>Agregar el primer cliente</button>
    </div>`}
  </div>`;

  const pintar = () => {
    const caja = $("#lista-clientes", el);
    if (!caja) return;
    const q = sinTildes(buscar.trim());
    const lista = datos.clientes.filter((c) => !q || sinTildes(`${c.nombre} ${c.telefono}`).includes(q));
    caja.innerHTML = lista.length ? lista.map((c) => `
      <article class="cliente ${c.saldo > 0 ? "debe" : "al-dia"}">
        <button class="cliente-cuerpo" data-ver="${c.id}" aria-label="Ver la cuenta de ${esc(c.nombre)}">
          <span class="avatar">${esc(iniciales(c.nombre))}</span>
          <span class="cliente-datos">
            <b>${esc(c.nombre)}</b>
            <small class="tenue">${c.telefono ? esc(c.telefono) + " · " : ""}${esc(cuando(c.ultimo_movimiento))}</small>
          </span>
          <span class="cliente-saldo">${c.saldo > 0 ? `<small>Debe</small><b class="precio">${dinero(c.saldo)}</b>` : '<span class="etiqueta verde">Al día</span>'}</span>
        </button>
        ${c.saldo > 0 ? `<div class="cliente-acciones">
          ${c.telefono ? `<a class="btn btn-chico" href="${enlaceWhatsApp(c)}" target="_blank" rel="noopener">Recordar por WhatsApp</a>` : ""}
          <button class="btn btn-chico btn-rojo" data-abonar="${c.id}">Abonar</button>
        </div>` : ""}
      </article>`).join("") : `<p class="nada">No hay clientes con “${esc(buscar)}”.</p>`;
  };
  pintar();

  const contenedor = el.firstElementChild;
  $("#buscar-cliente", contenedor)?.addEventListener("input", (e) => { buscar = e.target.value; pintar(); });
  contenedor.addEventListener("click", (e) => {
    if (e.target.closest("#nuevo-cliente, [data-nuevo]")) return formularioCliente(null, () => mostrarFiados(raiz, sesion));
    const ver = e.target.closest("[data-ver]");
    if (ver) return cuenta(Number(ver.dataset.ver));
    const abonar = e.target.closest("[data-abonar]");
    if (abonar) return abonarModal(datos.clientes.find((c) => c.id === Number(abonar.dataset.abonar)));
  });
}

// ---------- Crear o editar cliente (también se usa desde Vender) ----------
export function formularioCliente(cliente, alGuardar) {
  const c = cliente || { nombre: "", telefono: "", nota: "" };
  const m = abrirModal(`
    <h2>${cliente ? "Editar cliente" : "Nuevo cliente"}</h2>
    <form id="f-cliente" class="form-producto" novalidate>
      <label class="campo">Nombre<input id="c-nombre" required value="${esc(c.nombre)}" placeholder="Juan Pérez" autocomplete="off"></label>
      <label class="campo">Celular (opcional, para recordarle por WhatsApp)<input id="c-telefono" inputmode="tel" value="${esc(c.telefono)}" placeholder="0991234567" autocomplete="off"></label>
      <label class="campo">Nota (opcional)<input id="c-nota" value="${esc(c.nota)}" placeholder="Vive en la esquina, paga los viernes" autocomplete="off"></label>
      <p class="error-form error-claro" id="c-error" role="alert"></p>
      <div class="acciones"><button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn btn-rojo">Guardar</button></div>
    </form>`);
  $("#c-nombre", m).focus();
  $("#f-cliente", m).addEventListener("submit", async (e) => {
    e.preventDefault();
    const datos = { nombre: $("#c-nombre", m).value.trim(), telefono: $("#c-telefono", m).value.trim(), nota: $("#c-nota", m).value.trim() };
    if (datos.nombre.length < 2) { $("#c-error", m).textContent = "Escribe el nombre del cliente."; return; }
    try {
      const guardado = cliente ? await api.put(`/api/clientes/${cliente.id}`, datos) : await api.post("/api/clientes", datos);
      cerrarModal();
      avisar(cliente ? "Cliente guardado" : `${guardado.nombre} agregado`);
      alGuardar?.(guardado);
    } catch (err) { $("#c-error", m).textContent = err.message; }
  });
}

// ---------- Cuenta del cliente ----------
async function cuenta(id) {
  const m = abrirModal(`<h2>Cuenta</h2>${cargando()}`);
  let c;
  try { c = await api.get(`/api/clientes/${id}`); }
  catch (e) { avisar(e.message, "error"); cerrarModal(); return; }
  const admin = sesion.rol === "admin";
  m.innerHTML = `
    <div class="cuenta-cabeza">
      <span class="avatar">${esc(iniciales(c.nombre))}</span>
      <div><h2>${esc(c.nombre)}</h2><p class="tenue">${esc([c.telefono, c.nota].filter(Boolean).join(" · ")) || "Sin teléfono"}</p></div>
    </div>
    <div class="cuenta-saldo ${c.saldo > 0 ? "debe" : ""}">
      <small>${c.saldo > 0 ? "Debe" : "Está al día"}</small><b>${dinero(c.saldo)}</b>
      <span class="tenue">Llevó fiado ${dinero(c.fiado)} · abonó ${dinero(c.abonado)}</span>
    </div>
    <div class="acciones cuenta-botones">
      ${c.saldo > 0 ? `<button class="btn btn-rojo" data-abonar>Abonar</button>` : ""}
      ${c.saldo > 0 ? `<a class="btn" href="${enlaceWhatsApp(c)}" target="_blank" rel="noopener">WhatsApp</a>` : ""}
      <button class="btn" data-editar>Editar</button>
      ${admin && c.saldo <= 0 ? '<button class="enlace eliminar" data-eliminar>Quitar cliente</button>' : ""}
    </div>
    <h3 class="subtitulo">Movimientos</h3>
    <ul class="historial cuenta-historial">${c.cuenta.map((x) => `
      <li class="${x.anulado ? "anulado" : ""}">
        <span class="mov ${x.tipo === "fiado" ? "baja" : "sube"}">${x.tipo === "fiado" ? "+" : "−"}${dinero(x.monto)}</span>
        <div><b>${x.tipo === "fiado" ? "Llevó fiado" : esc(x.detalle)}</b>
          <small class="tenue">${esc(x.fecha)} ${esc(x.hora)}${x.usuario ? " · " + esc(x.usuario) : ""}${x.tipo === "fiado" ? " · " + esc(x.detalle) : ""}${x.anulado ? " · anulado" : ""}</small></div>
        ${admin && x.tipo === "abono" && !x.anulado ? `<button class="enlace eliminar" data-anular-abono="${x.id}">Anular</button>` : "<span></span>"}
      </li>`).join("") || "<li>Todavía no tiene movimientos.</li>"}
    </ul>
    <div class="acciones"><button class="btn" data-cerrar>Cerrar</button></div>`;

  m.addEventListener("click", async (e) => {
    if (e.target.closest("[data-abonar]")) return abonarModal(c);
    if (e.target.closest("[data-editar]")) return formularioCliente(c, () => mostrarFiados(raiz, sesion));
    if (e.target.closest("[data-eliminar]")) {
      cerrarModal();
      if (!(await confirmar("¿Quitar cliente?", `${c.nombre} ya no aparecerá en la lista. Su historial se conserva.`, "Sí, quitar"))) return;
      try { await api.borrar(`/api/clientes/${c.id}`); avisar("Cliente quitado"); mostrarFiados(raiz, sesion); }
      catch (err) { avisar(err.message, "error"); }
      return;
    }
    const anular = e.target.closest("[data-anular-abono]");
    if (anular) {
      cerrarModal();
      if (!(await confirmar("¿Anular este abono?", "La deuda del cliente vuelve a subir por ese valor.", "Sí, anular"))) return;
      try { await api.post(`/api/abonos/${anular.dataset.anularAbono}/anular`); avisar("Abono anulado"); mostrarFiados(raiz, sesion); }
      catch (err) { avisar(err.message, "error"); }
    }
  });
}

// ---------- Abonar ----------
function abonarModal(c) {
  let metodo = "Efectivo";
  const m = abrirModal(`
    <h2>Abono de ${esc(c.nombre.split(" ")[0])}</h2>
    <p class="tenue">Debe <b class="precio">${dinero(c.saldo)}</b></p>
    <label class="campo">¿Cuánto paga?<input id="a-monto" class="entrada grande-entrada" inputmode="decimal" placeholder="${dinero(c.saldo)}" autocomplete="off"></label>
    <div class="billetes">
      <button type="button" class="chip" data-monto="${c.saldo}">Todo (${dinero(c.saldo)})</button>
      ${[500, 1000, 2000].filter((x) => x < c.saldo).map((x) => `<button type="button" class="chip" data-monto="${x}">${dinero(x)}</button>`).join("")}
    </div>
    <div class="metodos" role="radiogroup" aria-label="Cómo paga">
      ${["Efectivo", "Deuna"].map((x) => `<button type="button" class="metodo ${x === metodo ? "activo" : ""}" data-metodo="${x}" role="radio" aria-checked="${x === metodo}">${x}</button>`).join("")}
    </div>
    <p class="resultado" id="a-queda"></p>
    <p class="error-form error-claro" id="a-error" role="alert"></p>
    <div class="acciones"><button class="btn" data-cerrar>Cancelar</button><button class="btn btn-rojo" id="a-guardar">Registrar abono</button></div>`);
  const monto = $("#a-monto", m);
  monto.focus();
  const actualizar = () => {
    const v = aCentavos(monto.value);
    $("#a-error", m).textContent = "";
    $("#a-queda", m).innerHTML = !v ? "" : v > c.saldo ? `<span class="falta">Solo debe ${dinero(c.saldo)}</span>`
      : v === c.saldo ? `Queda <b class="sube">al día</b>` : `Queda debiendo <b>${dinero(c.saldo - v)}</b>`;
  };
  monto.addEventListener("input", actualizar);
  m.addEventListener("click", async (e) => {
    const chip = e.target.closest("[data-monto]");
    if (chip) { monto.value = (Number(chip.dataset.monto) / 100).toFixed(2).replace(".", ","); actualizar(); return; }
    const met = e.target.closest("[data-metodo]");
    if (met) {
      metodo = met.dataset.metodo;
      m.querySelectorAll("[data-metodo]").forEach((b) => { b.classList.toggle("activo", b === met); b.setAttribute("aria-checked", b === met); });
      return;
    }
    if (e.target.closest("#a-guardar")) {
      const v = aCentavos(monto.value);
      if (!v) { $("#a-error", m).textContent = "Escribe cuánto está pagando."; return; }
      if (v > c.saldo) { $("#a-error", m).textContent = `${c.nombre} solo debe ${dinero(c.saldo)}.`; return; }
      try {
        const nuevo = await api.post(`/api/clientes/${c.id}/abonos`, { monto: v, metodo });
        cerrarModal();
        celebrar("Abono registrado", nuevo.saldo > 0 ? `${nuevo.nombre.split(" ")[0]} ahora debe ${dinero(nuevo.saldo)}` : `${nuevo.nombre.split(" ")[0]} quedó al día`, 2000);
        if (location.hash === "#fiados") mostrarFiados(raiz, sesion);
      } catch (err) { $("#a-error", m).textContent = err.message; }
    }
  });
}
