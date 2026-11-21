// Pantallas de Ingresar y Crear cuenta.
// La primera vez que se abre la app (sin usuarios) pide crear la cuenta del administrador.

import { api } from "./api.js";
import { esc, MANO } from "./ui.js";

const OJO = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';

const campoClave = (id, etiqueta, autocompletar) => `
  <label class="campo">${etiqueta}
    <span class="con-boton">
      <input id="${id}" type="password" autocomplete="${autocompletar}" required minlength="6">
      <button type="button" class="ver-clave" data-ver="${id}" aria-label="Mostrar contraseña">${OJO}</button>
    </span>
  </label>`;

const FORMULARIOS = {
  ingresar: () => `
    <h1 class="acceso-titulo">Ingresar</h1>
    <label class="campo">Usuario<input id="usuario" autocomplete="username" autocapitalize="none" spellcheck="false" required></label>
    ${campoClave("clave", "Contraseña", "current-password")}
    <p class="error-form" id="error" role="alert"></p>
    <button class="btn btn-rojo btn-ancho" id="enviar">Ingresar</button>
    <button type="button" class="enlace cambiar" data-ir="registro">¿No tienes cuenta? Crear una</button>`,

  registro: (primera) => `
    <h1 class="acceso-titulo">${primera ? "Crea la cuenta del administrador" : "Crear cuenta"}</h1>
    ${primera ? '<p class="nota-acceso">Es la primera vez que se abre la app. Esta cuenta podrá ver todo y aprobar a los vendedores.</p>' : ""}
    <label class="campo">Tu nombre<input id="nombre" autocomplete="name" required placeholder="María Muñoz"></label>
    <label class="campo">Usuario para ingresar<input id="usuario" autocomplete="username" autocapitalize="none" spellcheck="false" required placeholder="maria"></label>
    ${campoClave("clave", "Contraseña (mínimo 6 caracteres)", "new-password")}
    ${campoClave("clave2", "Repite la contraseña", "new-password")}
    <p class="error-form" id="error" role="alert"></p>
    <button class="btn btn-rojo btn-ancho" id="enviar">Crear cuenta</button>
    ${primera ? "" : '<button type="button" class="enlace cambiar" data-ir="ingresar">Ya tengo cuenta, ingresar</button>'}`,

  pendiente: (nombre) => `
    <div class="pendiente">
      <div class="octagono chico"><div>${MANO}</div></div>
      <h1 class="acceso-titulo">Cuenta creada</h1>
      <p>${esc(nombre)}, tu cuenta está esperando que el administrador la apruebe. Cuando lo haga, ya podrás ingresar.</p>
      <button type="button" class="btn btn-ancho" data-ir="ingresar">Volver a ingresar</button>
    </div>`,
};

export async function mostrarAcceso(el, alEntrar) {
  let primera = false;
  try { primera = !(await api.get("/api/auth/estado")).hay_usuarios; } catch { /* sin conexión: se muestra ingresar */ }

  el.innerHTML = `
    <div class="acceso">
      <img class="hueco" src="img/logo_muro.jpg" alt="Stop 44 licorería">
      <form class="panel-roto formulario-acceso" id="form-acceso" novalidate></form>
    </div>`;
  const form = el.querySelector("#form-acceso");

  function ir(vista, dato) {
    form.dataset.vista = vista;
    form.innerHTML = vista === "registro" ? FORMULARIOS.registro(primera) : FORMULARIOS[vista](dato);
    form.classList.remove("entra"); void form.offsetWidth; form.classList.add("entra");
    form.querySelector("input")?.focus();
  }

  form.addEventListener("click", (e) => {
    const ver = e.target.closest("[data-ver]");
    if (ver) {
      const input = form.querySelector("#" + ver.dataset.ver);
      input.type = input.type === "password" ? "text" : "password";
      ver.classList.toggle("activo", input.type === "text");
      ver.setAttribute("aria-label", input.type === "text" ? "Ocultar contraseña" : "Mostrar contraseña");
    }
    const destino = e.target.closest("[data-ir]");
    if (destino) ir(destino.dataset.ir);
  });

  form.addEventListener("input", () => { form.querySelector("#error").textContent = ""; });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const valor = (id) => form.querySelector("#" + id)?.value ?? "";
    const error = form.querySelector("#error");
    const boton = form.querySelector("#enviar");
    const vista = form.dataset.vista;

    if (!valor("usuario").trim() || !valor("clave")) { error.textContent = "Escribe tu usuario y tu contraseña."; return; }
    if (vista === "registro") {
      if (!valor("nombre").trim()) { error.textContent = "Escribe tu nombre."; return; }
      if (valor("clave").length < 6) { error.textContent = "La contraseña debe tener al menos 6 caracteres."; return; }
      if (valor("clave") !== valor("clave2")) { error.textContent = "Las contraseñas no coinciden."; return; }
    }

    const textoBoton = boton.textContent;
    boton.disabled = true;
    boton.textContent = vista === "registro" ? "Creando cuenta…" : "Ingresando…";
    try {
      if (vista === "registro") {
        const r = await api.post("/api/auth/registro", { nombre: valor("nombre"), usuario: valor("usuario"), clave: valor("clave") });
        if (r.usuario.estado === "activo") alEntrar(r.usuario, true);
        else { primera = false; ir("pendiente", r.usuario.nombre); }
      } else {
        const r = await api.post("/api/auth/ingresar", { usuario: valor("usuario"), clave: valor("clave") });
        alEntrar(r.usuario, false);
      }
    } catch (err) {
      error.textContent = err.message;
      form.classList.remove("tiembla"); void form.offsetWidth; form.classList.add("tiembla");
      boton.disabled = false;
      boton.textContent = textoBoton;
    }
  });

  ir(primera ? "registro" : "ingresar");
}
