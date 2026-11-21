// Pantalla de Usuarios (solo administrador): aprobar cuentas nuevas, cambiar
// el rol, desactivar y poner una contraseña nueva a quien la olvidó.

import { api } from "./api.js";
import { $, esc, avisar, abrirModal, cerrarModal, confirmar, celebrar, cargando } from "./ui.js";

let raiz = null, sesion = null;

const ROL = { admin: "Administrador", vendedor: "Vendedor" };
const ESTADO = { activo: ["Activo", "verde"], pendiente: ["Esperando aprobación", "ambar"], inactivo: ["Desactivado", "roja"] };
const iniciales = (n) => n.split(" ").filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");

export async function mostrarUsuarios(el, usuario) {
  raiz = el; sesion = usuario;
  el.innerHTML = cargando();
  let lista;
  try { lista = await api.get("/api/usuarios"); }
  catch (e) { el.innerHTML = `<div class="panel-roto vacio"><p>${esc(e.message)}</p></div>`; return; }

  const pendientes = lista.filter((u) => u.estado === "pendiente");
  const resto = lista.filter((u) => u.estado !== "pendiente");

  el.innerHTML = `<div class="pantalla-usuarios">
    <h1 class="titulo">Usuarios</h1>

    ${pendientes.length ? `
    <section class="panel-roto pendientes">
      <h2 class="subtitulo">${pendientes.length === 1 ? "1 cuenta espera" : `${pendientes.length} cuentas esperan`} tu aprobación</h2>
      ${pendientes.map((u) => `
        <div class="pendiente-fila">
          <span class="avatar">${esc(iniciales(u.nombre))}</span>
          <div class="usuario-datos"><b>${esc(u.nombre)}</b><small>@${esc(u.usuario)} · se registró el ${esc(u.creado.slice(0, 10))}</small></div>
          <div class="usuario-acciones">
            <button class="btn btn-chico" data-rechazar="${u.id}">Rechazar</button>
            <button class="btn btn-chico btn-rojo" data-aprobar="${u.id}">Aprobar</button>
          </div>
        </div>`).join("")}
    </section>` : ""}

    <div class="lista-usuarios">
      ${resto.map((u) => {
        const [estado, color] = ESTADO[u.estado];
        const soyYo = u.id === sesion.id;
        return `
        <article class="usuario ${u.estado}">
          <span class="avatar ${u.rol}">${esc(iniciales(u.nombre))}</span>
          <div class="usuario-datos">
            <b>${esc(u.nombre)}${soyYo ? ' <span class="tenue">(tú)</span>' : ""}</b>
            <small>@${esc(u.usuario)} · ${ROL[u.rol]}</small>
            ${u.estado !== "activo" ? `<span class="etiqueta ${color}">${estado}</span>` : ""}
          </div>
          <div class="usuario-acciones">
            ${u.estado === "activo" ? `
              <button class="btn btn-chico" data-rol="${u.id}" data-nuevo-rol="${u.rol === "admin" ? "vendedor" : "admin"}">${u.rol === "admin" ? "Volver vendedor" : "Hacer administrador"}</button>
              <button class="btn btn-chico" data-clave="${u.id}">Nueva contraseña</button>
              ${soyYo ? "" : `<button class="btn btn-chico peligro" data-desactivar="${u.id}">Desactivar</button>`}`
            : `<button class="btn btn-chico btn-rojo" data-aprobar="${u.id}">Reactivar</button>`}
          </div>
        </article>`;
      }).join("")}
    </div>

    <p class="tenue ayuda-usuarios">Para que alguien nuevo use la app, pídele que entre al enlace y toque <b>Crear una</b>. Su cuenta aparecerá aquí para que la apruebes.</p>

    <section class="sticker respaldo">
      <h2 class="subtitulo">Copia de seguridad</h2>
      <p class="tenue">Descarga un archivo con todo: productos, fotos, ventas y usuarios. Guárdalo en el computador o en Google Drive de vez en cuando, por ejemplo cada semana.</p>
      <a class="btn" href="/api/respaldo" download>Descargar copia</a>
    </section>
  </div>`;

  const nombre = (id) => lista.find((u) => u.id === id)?.nombre;
  const cambiar = async (id, datos, mensaje) => {
    try { await api.patch(`/api/usuarios/${id}`, datos); avisar(mensaje); await mostrarUsuarios(raiz, sesion); actualizarAviso(); }
    catch (e) { avisar(e.message, "error"); }
  };

  el.firstElementChild.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const id = Number(b.dataset.aprobar || b.dataset.rechazar || b.dataset.rol || b.dataset.clave || b.dataset.desactivar);
    if (b.dataset.aprobar) {
      await cambiar(id, { estado: "activo" }, `${nombre(id)} ya puede ingresar`);
    } else if (b.dataset.rechazar) {
      if (await confirmar("¿Rechazar esta cuenta?", `${nombre(id)} no podrá ingresar. Puedes reactivarla después si te equivocas.`, "Sí, rechazar"))
        await cambiar(id, { estado: "inactivo" }, "Cuenta rechazada");
    } else if (b.dataset.rol) {
      const rol = b.dataset.nuevoRol;
      const texto = rol === "admin"
        ? `${nombre(id)} podrá ver costos y ganancias, editar el inventario, anular ventas y manejar usuarios.`
        : `${nombre(id)} solo podrá vender y ver sus ventas.`;
      if (await confirmar(rol === "admin" ? "¿Hacer administrador?" : "¿Volver vendedor?", texto, "Sí, cambiar"))
        await cambiar(id, { rol }, `${nombre(id)} ahora es ${ROL[rol].toLowerCase()}`);
    } else if (b.dataset.desactivar) {
      if (await confirmar("¿Desactivar esta cuenta?", `${nombre(id)} ya no podrá ingresar. Sus ventas se conservan.`, "Sí, desactivar"))
        await cambiar(id, { estado: "inactivo" }, "Cuenta desactivada");
    } else if (b.dataset.clave) {
      nuevaClave(id, nombre(id));
    }
  });
}

function nuevaClave(id, nombre) {
  const m = abrirModal(`
    <h2>Nueva contraseña</h2>
    <p class="tenue">Para ${esc(nombre)}. Dásela en persona y pídele que la cambie al entrar.</p>
    <form id="f-clave" class="form-producto" novalidate>
      <label class="campo">Contraseña nueva<input id="c-nueva" autocomplete="new-password" minlength="6" required></label>
      <p class="error-form error-claro" id="c-error" role="alert"></p>
      <div class="acciones"><button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn btn-rojo">Guardar</button></div>
    </form>`);
  $("#f-clave", m).addEventListener("submit", async (e) => {
    e.preventDefault();
    const nueva = $("#c-nueva", m).value;
    if (nueva.length < 6) { $("#c-error", m).textContent = "Debe tener al menos 6 caracteres."; return; }
    try { await api.post(`/api/usuarios/${id}/clave`, { nueva }); cerrarModal(); avisar(`Contraseña de ${nombre} cambiada`); }
    catch (err) { $("#c-error", m).textContent = err.message; }
  });
}

// Cambiar la contraseña propia (cualquier usuario, desde su nombre arriba)
export function cambiarMiClave() {
  const m = abrirModal(`
    <h2>Cambiar mi contraseña</h2>
    <form id="f-mi-clave" class="form-producto" novalidate>
      <label class="campo">Contraseña actual<input id="m-actual" type="password" autocomplete="current-password" required></label>
      <label class="campo">Contraseña nueva (mínimo 6)<input id="m-nueva" type="password" autocomplete="new-password" required></label>
      <label class="campo">Repite la nueva<input id="m-nueva2" type="password" autocomplete="new-password" required></label>
      <p class="error-form error-claro" id="m-error" role="alert"></p>
      <div class="acciones"><button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn btn-rojo">Cambiar</button></div>
    </form>`);
  $("#f-mi-clave", m).addEventListener("submit", async (e) => {
    e.preventDefault();
    const [actual, nueva, nueva2] = ["#m-actual", "#m-nueva", "#m-nueva2"].map((s) => $(s, m).value);
    const error = $("#m-error", m);
    if (nueva.length < 6) { error.textContent = "La contraseña nueva debe tener al menos 6 caracteres."; return; }
    if (nueva !== nueva2) { error.textContent = "Las contraseñas nuevas no coinciden."; return; }
    try { await api.post("/api/auth/clave", { actual, nueva }); cerrarModal(); celebrar("Contraseña cambiada", "", 1300); }
    catch (err) { error.textContent = err.message; }
  });
}

// Numerito rojo en "Usuarios" cuando hay cuentas esperando aprobación
export async function actualizarAviso() {
  try {
    const lista = await api.get("/api/usuarios");
    const n = lista.filter((u) => u.estado === "pendiente").length;
    const enlace = document.querySelector('.nav a[href="#usuarios"]');
    if (!enlace) return;
    enlace.querySelector(".insignia")?.remove();
    if (n) enlace.insertAdjacentHTML("beforeend", `<span class="insignia" aria-label="${n} pendientes">${n}</span>`);
  } catch { /* sin permiso o sin conexión: no se muestra nada */ }
}
