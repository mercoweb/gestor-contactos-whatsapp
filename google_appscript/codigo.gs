const APP_URL = "URL_DE_TU_APP"; // ej: https://tu-app.com
const APP_TOKEN = "TOKEN_SECRETO_DE_LA_APP"; // igual al APP_TOKEN del .env

function telefonoDeLaRespuesta(respuestas, items) {
  for (const item of items) {
    const titulo = (item.title || "").toLowerCase();
    if (titulo.includes("tel") || titulo.includes("phone")) {
      return String(respuestas[item.id] || "").trim();
    }
  }
  return "";
}

function valorPorTitulo(respuestas, items, palabrasClave) {
  for (const item of items) {
    const titulo = (item.title || "").toLowerCase();
    if (palabrasClave.some((p) => titulo.includes(p))) {
      const valor = respuestas[item.id];
      return Array.isArray(valor) ? valor.join(", ") : String(valor || "").trim();
    }
  }
  return "";
}

function alEnviarFormulario(evento) {
  const respuestas = evento.response.getItemResponses();
  const items = respuestas.map((r) => ({ title: r.getItem().getTitle(), id: r.getItem().getId() }));
  const mapa = {};
  respuestas.forEach((r) => {
    mapa[r.getItem().getId()] = r.getResponse();
  });

  const telefono = telefonoDeLaRespuesta(mapa, items);
  if (!telefono) {
    console.warn("Respuesta sin teléfono; se ignora.");
    return;
  }

  const datos = {
    telefono: telefono,
    nombre: valorPorTitulo(mapa, items, ["nombre"]),
    email: valorPorTitulo(mapa, items, ["email", "correo"]),
    ciudad: valorPorTitulo(mapa, items, ["ciudad", "city"]),
  };

  UrlFetchApp.fetch(APP_URL + "/api/webhook/formulario", {
    method: "post",
    contentType: "application/json",
    headers: { "X-App-Token": APP_TOKEN },
    payload: JSON.stringify(datos),
    muteHttpExceptions: true,
  });
}
