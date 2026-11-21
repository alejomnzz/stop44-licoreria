// Comunicación con la API de Python (FastAPI).
// La sesión viaja sola en una cookie, así que aquí no se maneja ningún token.

export class ErrorApi extends Error {
  constructor(mensaje, estado) {
    super(mensaje);
    this.estado = estado;          // 400 = dato inválido, 401 = sin sesión, 403 = sin permiso
  }
}

async function pedir(metodo, ruta, datos) {
  let respuesta;
  try {
    respuesta = await fetch(ruta, {
      method: metodo,
      headers: datos ? { "Content-Type": "application/json" } : {},
      body: datos ? JSON.stringify(datos) : undefined,
      credentials: "same-origin",
    });
  } catch {
    throw new ErrorApi("No hay conexión con el servidor. Revisa el internet e intenta de nuevo.", 0);
  }
  const cuerpo = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    let mensaje = cuerpo.detail;
    if (Array.isArray(mensaje)) mensaje = "Revisa los datos del formulario.";   // error de validación
    throw new ErrorApi(mensaje || "Algo salió mal. Intenta de nuevo.", respuesta.status);
  }
  return cuerpo;
}

export const api = {
  get: (ruta) => pedir("GET", ruta),
  post: (ruta, datos = {}) => pedir("POST", ruta, datos),
  put: (ruta, datos) => pedir("PUT", ruta, datos),
  patch: (ruta, datos) => pedir("PATCH", ruta, datos),
  borrar: (ruta) => pedir("DELETE", ruta),
};
