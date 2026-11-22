// Service worker: guarda los archivos de la app en el celular para que abra
// rápido y siga mostrándose aunque el internet falle un momento.
// Las ventas y el inventario SIEMPRE se piden al servidor (nunca se guardan aquí).

const VERSION = "stop44-v5";
const ARCHIVOS = [
  "/", "/css/estilos.css", "/manifest.json",
  "/js/app.js", "/js/api.js", "/js/ui.js", "/js/dibujos.js", "/js/acceso.js",
  "/js/vender.js", "/js/inventario.js", "/js/ventas.js", "/js/resumen.js", "/js/usuarios.js", "/js/fiados.js",
  "/img/logo_muro.jpg", "/img/logo_letras.jpg", "/img/ladrillos.svg", "/img/icono-192.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(ARCHIVOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((nombres) => Promise.all(nombres.filter((n) => n !== VERSION).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const pedido = e.request;
  if (pedido.method !== "GET") return;                       // ventas, cambios: directo al servidor
  const url = new URL(pedido.url);

  // Fotos de productos: no cambian (llevan ?v=versión), se guardan una vez
  if (url.pathname.match(/^\/api\/productos\/\d+\/foto$/)) {
    e.respondWith(caches.open(VERSION).then(async (c) => {
      const guardada = await c.match(pedido);
      if (guardada) return guardada;
      const r = await fetch(pedido);
      if (r.ok) c.put(pedido, r.clone());
      return r;
    }));
    return;
  }

  // Datos de la API: siempre del servidor
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/docs")) return;

  // Archivos de la app y fuentes: primero internet (para tener siempre la última versión),
  // y si no hay conexión, lo guardado
  e.respondWith(
    fetch(pedido)
      .then((r) => {
        if (r.ok && (url.origin === location.origin || url.hostname.endsWith("gstatic.com") || url.hostname.endsWith("googleapis.com"))) {
          const copia = r.clone();
          caches.open(VERSION).then((c) => c.put(pedido, copia));
        }
        return r;
      })
      .catch(() => caches.match(pedido).then((r) => r || caches.match("/")))
  );
});
