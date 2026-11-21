// Pantalla de Inventario (solo administrador): productos, fotos, entradas de
// mercancía, conteos físicos e historial de cada producto.

import { api } from "./api.js";
import { $, esc, dinero, aCentavos, avisar, abrirModal, cerrarModal, confirmar, celebrar, cargando } from "./ui.js";
import { imagenProducto, dibujoProducto } from "./dibujos.js";

const CAMARA = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M3 8h4l2-3h6l2 3h4v12H3z"/><circle cx="12" cy="13" r="4"/></svg>';
const estado = { productos: [], categorias: [], valor: null, buscar: "", categoria: "Todo", soloPedir: false };
let raiz = null;

const producto = (id) => estado.productos.find((p) => p.id === id);
const sinTildes = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const aTexto = (centavos) => (centavos ? (centavos / 100).toFixed(2).replace(".", ",") : "");

export async function mostrarInventario(el) {
  raiz = el;
  el.innerHTML = cargando();
  try {
    const [productos, catalogo, valor] = await Promise.all([
      api.get("/api/productos"), api.get("/api/catalogo"), api.get("/api/inventario/valor")]);
    Object.assign(estado, { productos, categorias: catalogo.categorias, valor });
  } catch (e) {
    el.innerHTML = `<div class="panel-roto vacio"><p>${esc(e.message)}</p></div>`;
    return;
  }
  const porPedir = estado.productos.filter((p) => p.stock_bajo).length;
  el.innerHTML = `<div class="pantalla-inventario">
    <div class="encabezado">
      <h1 class="titulo">Inventario</h1>
      <button class="btn btn-rojo" id="nuevo">+ Nuevo producto</button>
    </div>
    <div class="cifras">
      <div class="cifra"><small>Productos</small><b>${estado.productos.length}</b></div>
      <div class="cifra"><small>Unidades</small><b>${estado.valor.unidades.toLocaleString("es-EC")}</b></div>
      <div class="cifra"><small>Invertido (a costo)</small><b>${dinero(estado.valor.a_costo)}</b></div>
      <div class="cifra"><small>Si se vende todo</small><b class="precio">${dinero(estado.valor.a_precio_venta)}</b></div>
      <button class="cifra ${porPedir ? "alerta" : ""}" id="ver-pedir"><small>Por pedir</small><b>${porPedir}</b></button>
    </div>
    <label class="buscador">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>
      <input id="buscar-inv" type="search" placeholder="Buscar por nombre o código" autocomplete="off" value="${esc(estado.buscar)}" aria-label="Buscar producto">
    </label>
    <div class="categorias" id="cats-inv"></div>
    <div class="lista-inventario" id="lista-inv"></div>
  </div>`;
  pintarFiltros();
  pintarLista();
  conectar();
}

function pintarFiltros() {
  const presentes = [...new Set(estado.productos.map((p) => p.categoria))].sort();
  if (estado.categoria !== "Todo" && !presentes.includes(estado.categoria)) estado.categoria = "Todo";
  $("#cats-inv", raiz).innerHTML =
    `<button class="chip ${estado.soloPedir ? "activo" : ""}" data-pedir>⚠ Por pedir</button>` +
    ["Todo", ...presentes].map((c) => `<button class="chip ${!estado.soloPedir && c === estado.categoria ? "activo" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("");
}

function pintarLista() {
  const caja = $("#lista-inv", raiz);
  if (!estado.productos.length) {
    caja.innerHTML = `<div class="panel-roto vacio"><p>Agrega los productos de la licorería: nombre, precio y cuántos hay. Si quieres, también una foto.</p><button class="btn btn-rojo" data-nuevo>Agregar el primero</button></div>`;
    return;
  }
  const q = sinTildes(estado.buscar.trim());
  const lista = estado.productos.filter((p) =>
    (estado.soloPedir ? p.stock_bajo : estado.categoria === "Todo" || p.categoria === estado.categoria) &&
    (!q || sinTildes(`${p.nombre} ${p.presentacion} ${p.codigo || ""}`).includes(q)));
  if (!lista.length) {
    caja.innerHTML = `<p class="nada">${estado.soloPedir ? "No hay nada por pedir. Todo está por encima del mínimo." : "No hay productos con ese filtro."}</p>`;
    return;
  }
  caja.innerHTML = lista.map((p) => {
    const tipo = p.stock <= 0 ? "roja" : p.stock_bajo ? "ambar" : "verde";
    return `
      <article class="fila-producto">
        <button class="fila-foto" data-editar="${p.id}" aria-label="Editar ${esc(p.nombre_completo)}">${imagenProducto(p)}</button>
        <div class="fila-datos">
          <b>${esc(p.nombre)}</b>
          <span class="tenue">${esc([p.presentacion, p.categoria].filter(Boolean).join(" · "))}</span>
          <span class="fila-precios"><span class="precio">${dinero(p.precio)}</span>
            <span class="tenue">costo ${p.costo ? dinero(p.costo) : "—"}${p.margen != null ? ` · gana ${p.margen}%` : ""}</span></span>
        </div>
        <div class="fila-stock">
          <span class="stock-numero etiqueta ${tipo}">${p.stock}</span>
          <small class="tenue">mín. ${p.minimo}</small>
        </div>
        <div class="fila-acciones">
          <button class="btn btn-chico btn-rojo" data-entrada="${p.id}">+ Entrada</button>
          <button class="btn btn-chico" data-editar="${p.id}">Editar</button>
        </div>
      </article>`;
  }).join("");
}

// ---------- Formulario de producto (nuevo o editar) ----------
function formulario(id) {
  const p = id ? producto(id) : { nombre: "", categoria: estado.categoria !== "Todo" ? estado.categoria : "Aguardiente", presentacion: "", codigo: "", costo: 0, precio: 0, stock: 0, minimo: 5, foto: null };
  let fotoNueva = null;          // data URL de la foto elegida (ya achicada)
  let quitarFoto = false;

  const m = abrirModal(`
    <h2>${id ? "Editar producto" : "Nuevo producto"}</h2>
    <form id="form-prod" class="form-producto" novalidate>
      <div class="foto-campo">
        <div class="foto-vista" id="foto-vista">${id ? imagenProducto(p) : dibujoProducto(p.categoria)}</div>
        <div class="foto-botones">
          <label class="btn btn-chico">${CAMARA} ${p.foto ? "Cambiar foto" : "Agregar foto"}
            <input type="file" accept="image/*" id="foto-archivo" hidden>
          </label>
          ${p.foto ? '<button type="button" class="enlace" id="quitar-foto">Quitar foto</button>' : ""}
          <small class="tenue">Desde el celular puedes tomarla con la cámara.</small>
        </div>
      </div>
      <label class="campo">Nombre<input id="f-nombre" required value="${esc(p.nombre)}" placeholder="Aguardiente Norteño"></label>
      <div class="dos">
        <label class="campo">Categoría<select id="f-categoria">${estado.categorias.map((c) => `<option ${c === p.categoria ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>
        <label class="campo">Presentación<input id="f-presentacion" value="${esc(p.presentacion)}" placeholder="750 ml"></label>
      </div>
      <div class="dos">
        <label class="campo">Le cuesta a la tienda<input id="f-costo" inputmode="decimal" value="${aTexto(p.costo)}" placeholder="9,50"></label>
        <label class="campo">Precio de venta<input id="f-precio" inputmode="decimal" required value="${aTexto(p.precio)}" placeholder="12,50"></label>
      </div>
      <p class="margen" id="f-margen"></p>
      <div class="dos">
        <label class="campo">${id ? "Stock actual" : "Cuántos hay ahora"}<input id="f-stock" inputmode="numeric" value="${p.stock || ""}" placeholder="0"></label>
        <label class="campo">Avisar cuando queden<input id="f-minimo" inputmode="numeric" value="${p.minimo}"></label>
      </div>
      <label class="campo">Código de barras (opcional)<input id="f-codigo" value="${esc(p.codigo || "")}" placeholder="Escanéalo aquí" autocomplete="off"></label>
      <p class="error-form error-claro" id="f-error" role="alert"></p>
      <div class="acciones">
        ${id ? '<button type="button" class="enlace eliminar" id="eliminar">Eliminar</button><button type="button" class="enlace" id="historial">Ver historial</button><span class="espacio"></span>' : ""}
        <button type="button" class="btn" data-cerrar>Cancelar</button>
        <button class="btn btn-rojo" id="guardar">Guardar</button>
      </div>
    </form>`);

  if (!id) $("#f-nombre", m).focus();
  const v = (sel) => $(sel, m).value;
  const margen = () => {
    const costo = aCentavos(v("#f-costo")), precio = aCentavos(v("#f-precio"));
    const el = $("#f-margen", m);
    if (!costo || !precio) { el.textContent = ""; return; }
    const ganancia = precio - costo;
    el.innerHTML = ganancia > 0
      ? `Gana <b>${dinero(ganancia)}</b> por unidad (${Math.round((ganancia / precio) * 100)}%)`
      : `<span class="falta">Ojo: el precio de venta es menor que el costo.</span>`;
  };
  margen();
  m.addEventListener("input", (e) => {
    $("#f-error", m).textContent = "";
    if (e.target.matches("#f-costo, #f-precio")) margen();
  });
  $("#f-categoria", m).addEventListener("change", () => {
    if (!fotoNueva && (!p.foto || quitarFoto)) $("#foto-vista", m).innerHTML = dibujoProducto(v("#f-categoria"));
  });

  $("#foto-archivo", m).addEventListener("change", async (e) => {
    const archivo = e.target.files[0];
    if (!archivo) return;
    try {
      fotoNueva = await achicarFoto(archivo);
      quitarFoto = false;
      $("#foto-vista", m).innerHTML = `<img src="${fotoNueva}" alt="Foto nueva">`;
      $("#foto-vista", m).classList.remove("entra"); void m.offsetWidth; $("#foto-vista", m).classList.add("entra");
    } catch {
      avisar("No se pudo abrir esa foto. Prueba con otra.", "error");
    }
  });
  $("#quitar-foto", m)?.addEventListener("click", () => {
    quitarFoto = true; fotoNueva = null;
    $("#foto-vista", m).innerHTML = dibujoProducto(v("#f-categoria"));
  });

  $("#eliminar", m)?.addEventListener("click", async () => {
    cerrarModal();
    if (!(await confirmar("¿Eliminar producto?", `${p.nombre_completo} ya no aparecerá para vender. Las ventas pasadas se conservan.`, "Sí, eliminar"))) return;
    try { await api.borrar(`/api/productos/${id}`); avisar("Producto eliminado"); mostrarInventario(raiz); }
    catch (e) { avisar(e.message, "error"); }
  });
  $("#historial", m)?.addEventListener("click", () => historial(id));

  $("#form-prod", m).addEventListener("submit", async (e) => {
    e.preventDefault();
    const error = $("#f-error", m);
    const datos = {
      nombre: v("#f-nombre").trim(),
      categoria: v("#f-categoria"),
      presentacion: v("#f-presentacion").trim(),
      codigo: v("#f-codigo").trim() || null,
      costo: aCentavos(v("#f-costo")),
      precio: aCentavos(v("#f-precio")),
      stock: parseInt(v("#f-stock"), 10) || 0,
      minimo: parseInt(v("#f-minimo"), 10) || 0,
    };
    if (!datos.nombre) { error.textContent = "Escribe el nombre del producto."; return; }
    if (datos.precio <= 0) { error.textContent = "Escribe el precio de venta."; return; }

    const boton = $("#guardar", m);
    boton.disabled = true; boton.textContent = "Guardando…";
    try {
      const guardado = id ? await api.put(`/api/productos/${id}`, datos) : await api.post("/api/productos", datos);
      if (fotoNueva) await api.put(`/api/productos/${guardado.id}/foto`, { imagen: fotoNueva });
      else if (quitarFoto) await api.borrar(`/api/productos/${guardado.id}/foto`);
      cerrarModal();
      avisar(id ? "Producto guardado" : `${guardado.nombre} agregado al inventario`);
      mostrarInventario(raiz);
    } catch (err) {
      error.textContent = err.message;
      boton.disabled = false; boton.textContent = "Guardar";
    }
  });
}

// Achica la foto en el celular antes de subirla (máx. 700 px), así pesa poco y carga rápido
function achicarFoto(archivo, maximo = 700) {
  return new Promise((resolver, rechazar) => {
    const url = URL.createObjectURL(archivo);
    const img = new Image();
    img.onload = () => {
      const escala = Math.min(1, maximo / Math.max(img.width, img.height));
      const lienzo = document.createElement("canvas");
      lienzo.width = Math.round(img.width * escala);
      lienzo.height = Math.round(img.height * escala);
      const ctx = lienzo.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, lienzo.width, lienzo.height);
      ctx.drawImage(img, 0, 0, lienzo.width, lienzo.height);
      URL.revokeObjectURL(url);
      resolver(lienzo.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => { URL.revokeObjectURL(url); rechazar(new Error("imagen inválida")); };
    img.src = url;
  });
}

// ---------- Entrada de mercancía o conteo físico ----------
function entrada(id) {
  const p = producto(id);
  let tipo = "sumar";
  const m = abrirModal(`
    <h2>Entrada de mercancía</h2>
    <div class="entrada-cabeza">
      <div class="dibujo">${imagenProducto(p)}</div>
      <div><b>${esc(p.nombre_completo)}</b><p class="tenue">Ahora hay <b>${p.stock}</b></p></div>
    </div>
    <div class="metodos" role="radiogroup">
      <button type="button" class="metodo activo" data-tipo="sumar" role="radio" aria-checked="true">Llegó mercancía</button>
      <button type="button" class="metodo" data-tipo="fijar" role="radio" aria-checked="false">Conteo físico</button>
    </div>
    <p class="tenue" id="e-ayuda">Escribe cuántas unidades llegaron. Se suman a las que hay.</p>
    <div class="contador">
      <button type="button" class="btn" data-paso="-1" aria-label="Menos">−</button>
      <input id="e-cant" class="entrada" inputmode="numeric" value="" placeholder="0" aria-label="Cantidad">
      <button type="button" class="btn" data-paso="1" aria-label="Más">+</button>
    </div>
    <div class="paquetes">${[6, 12, 24].map((n) => `<button type="button" class="chip" data-suma="${n}">+${n}</button>`).join("")}</div>
    <label class="campo">Nuevo costo por unidad (opcional)<input id="e-costo" inputmode="decimal" placeholder="${aTexto(p.costo) || "9,50"}"></label>
    <p class="resultado" id="e-resultado"></p>
    <p class="error-form error-claro" id="e-error" role="alert"></p>
    <div class="acciones">
      <button class="btn" data-cerrar>Cancelar</button>
      <button class="btn btn-rojo" id="e-guardar">Guardar</button>
    </div>`);

  const cant = $("#e-cant", m);
  const actualizar = () => {
    const n = parseInt(cant.value, 10) || 0;
    const final = tipo === "fijar" ? n : p.stock + n;
    const diferencia = final - p.stock;
    $("#e-resultado", m).innerHTML = (cant.value === "" ? "" :
      `Quedarán <b>${final}</b> ${diferencia ? `<span class="${diferencia > 0 ? "sube" : "baja"}">(${diferencia > 0 ? "+" : ""}${diferencia})</span>` : ""}`);
    $("#e-error", m).textContent = "";
  };
  m.addEventListener("click", (e) => {
    const t = e.target.closest("[data-tipo]");
    if (t) {
      tipo = t.dataset.tipo;
      m.querySelectorAll("[data-tipo]").forEach((b) => { b.classList.toggle("activo", b === t); b.setAttribute("aria-checked", b === t); });
      $("#e-ayuda", m).textContent = tipo === "fijar"
        ? "Cuenta las unidades que hay en la tienda y escribe el total. El stock queda en ese número."
        : "Escribe cuántas unidades llegaron. Se suman a las que hay.";
      $(".paquetes", m).hidden = tipo === "fijar";
      actualizar();
    }
    const paso = e.target.closest("[data-paso]");
    if (paso) { cant.value = Math.max(0, (parseInt(cant.value, 10) || 0) + Number(paso.dataset.paso)); actualizar(); }
    const suma = e.target.closest("[data-suma]");
    if (suma) { cant.value = (parseInt(cant.value, 10) || 0) + Number(suma.dataset.suma); actualizar(); }
  });
  cant.addEventListener("input", actualizar);

  $("#e-guardar", m).addEventListener("click", async () => {
    const n = parseInt(cant.value, 10);
    if (Number.isNaN(n) || n < 0 || (tipo === "sumar" && n === 0)) { $("#e-error", m).textContent = "Escribe la cantidad."; return; }
    const costo = aCentavos($("#e-costo", m).value) || null;
    try {
      const nuevo = await api.post(`/api/productos/${id}/entrada`, { cantidad: n, costo, fijar: tipo === "fijar" });
      cerrarModal();
      celebrar(tipo === "fijar" ? "Conteo guardado" : "Mercancía agregada", `${nuevo.nombre_completo}: ahora hay ${nuevo.stock}`, 1500);
      mostrarInventario(raiz);
    } catch (err) { $("#e-error", m).textContent = err.message; }
  });
}

// ---------- Historial (kardex) ----------
const NOMBRES_MOV = { inicial: "Stock inicial", entrada: "Llegó mercancía", ajuste: "Ajuste", venta: "Venta", anulacion: "Venta anulada" };

async function historial(id) {
  const p = producto(id);
  const m = abrirModal(`<h2>Historial</h2><p class="tenue">${esc(p.nombre_completo)}</p>${cargando()}`);
  try {
    const movs = await api.get(`/api/productos/${id}/movimientos`);
    m.innerHTML = `<h2>Historial</h2><p class="tenue">${esc(p.nombre_completo)} · últimos ${movs.length} movimientos</p>
      <ul class="historial">${movs.map((x) => `
        <li><span class="mov ${x.cantidad > 0 ? "sube" : "baja"}">${x.cantidad > 0 ? "+" : ""}${x.cantidad}</span>
          <div><b>${NOMBRES_MOV[x.tipo] || esc(x.tipo)}</b><small class="tenue">${esc(x.fecha.slice(0, 16))}${x.usuario ? " · " + esc(x.usuario) : ""}${x.nota ? " · " + esc(x.nota) : ""}</small></div>
          <span class="tenue">quedan ${x.stock_final}</span></li>`).join("") || "<li>Sin movimientos todavía.</li>"}
      </ul>
      <div class="acciones"><button class="btn" data-cerrar>Cerrar</button></div>`;
  } catch (e) { avisar(e.message, "error"); cerrarModal(); }
}

// ---------- Eventos ----------
function conectar() {
  const caja = raiz.firstElementChild;
  $("#buscar-inv", caja).addEventListener("input", (e) => { estado.buscar = e.target.value; pintarLista(); });
  caja.addEventListener("click", (e) => {
    if (e.target.closest("#nuevo, [data-nuevo]")) return formulario(null);
    if (e.target.closest("#ver-pedir, [data-pedir]")) { estado.soloPedir = !estado.soloPedir || !!e.target.closest("#ver-pedir"); pintarFiltros(); pintarLista(); return; }
    const cat = e.target.closest("[data-cat]");
    if (cat) { estado.categoria = cat.dataset.cat; estado.soloPedir = false; pintarFiltros(); pintarLista(); return; }
    const editar = e.target.closest("[data-editar]");
    if (editar) return formulario(Number(editar.dataset.editar));
    const ent = e.target.closest("[data-entrada]");
    if (ent) return entrada(Number(ent.dataset.entrada));
  });
}
