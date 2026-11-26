require("dotenv").config();

const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");

const APP_URL = process.env.APP_URL || "http://localhost:8000";
const APP_TOKEN = process.env.APP_TOKEN || "cambia-este-token-secreto";
const GROUP_NAME = process.env.GROUP_NAME || "";
const MIN_DELAY_SECONDS = parseInt(process.env.MIN_DELAY_SECONDS || "90", 10);
const MAX_DELAY_SECONDS = parseInt(process.env.MAX_DELAY_SECONDS || "300", 10);
const DAILY_LIMIT = parseInt(process.env.DAILY_LIMIT || "150", 10);
const POLL_SECONDS = parseInt(process.env.POLL_SECONDS || "60", 10);

const hoy = () => new Date().toISOString().slice(0, 10);
let enviadosHoy = { fecha: hoy(), total: 0 };
let enviando = false;

const esperaAleatoria = () =>
  (MIN_DELAY_SECONDS + Math.random() * (MAX_DELAY_SECONDS - MIN_DELAY_SECONDS)) * 1000;

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(ruta, opciones = {}) {
  const resp = await fetch(`${APP_URL}${ruta}`, {
    ...opciones,
    headers: {
      "X-App-Token": APP_TOKEN,
      "Content-Type": "application/json",
      ...(opciones.headers || {}),
    },
  });
  if (!resp.ok) {
    throw new Error(`API ${ruta} respondió ${resp.status}`);
  }
  return resp.json();
}

function registrarEnvioDelDia() {
  const fecha = hoy();
  if (enviadosHoy.fecha !== fecha) {
    enviadosHoy = { fecha, total: 0 };
  }
  enviadosHoy.total += 1;
  return enviadosHoy.total;
}

const cliente = new Client({
  authStrategy: new LocalAuth({ dataPath: "session" }),
  puppeteer: { headless: true, args: ["--no-sandbox"] },
});

cliente.on("qr", (qr) => {
  console.log("Escanea este QR con WhatsApp (App > Dispositivos vinculados):");
  qrcode.generate(qr, { small: true });
});

cliente.on("ready", () => {
  console.log("Bot conectado a WhatsApp.");
  console.log(`Vigilando el grupo: "${GROUP_NAME || "(todos los grupos)"}"`);
  console.log(`Límite diario: ${DAILY_LIMIT} bienvenidas. Retardo entre envíos: ${MIN_DELAY_SECONDS}-${MAX_DELAY_SECONDS}s.`);
});

cliente.on("group_join", async (notificacion) => {
  try {
    const chat = await notificacion.getChat();
    if (GROUP_NAME && chat.name !== GROUP_NAME) return;
    const participantes = notificacion.recipientIds || [];
    if (!participantes.length) return;
    const telefonos = participantes.map((id) => id.split("@")[0]);
    console.log("Nuevo(s) miembro(s) en", chat.name, ":", telefonos.join(", "));
    const resultado = await api("/api/webhook/whatsapp-join", {
      method: "POST",
      body: JSON.stringify({ grupo: chat.name, participantes: telefonos, canal: "bot" }),
    });
    console.log("Registrado en la app:", JSON.stringify(resultado));
  } catch (error) {
    console.error("Error en group_join:", error.message);
  }
});

async function cicloEnvio() {
  if (enviando) return;
  enviando = true;
  try {
    if (enviadosHoy.fecha === hoy() && enviadosHoy.total >= DAILY_LIMIT) {
      console.log("Límite diario alcanzado. No se envían más mensajes hoy.");
      return;
    }
    const data = await api("/api/outbox/next");
    const mensaje = data.mensaje;
    if (!mensaje) return;

    await dormir(Math.random() * 5000);
    await cliente.sendMessage(`${mensaje.telefono}@c.us`, mensaje.texto);
    registrarEnvioDelDia();
    await api(`/api/outbox/${mensaje.id}/resultado`, {
      method: "POST",
      body: JSON.stringify({ estado: "enviado" }),
    });
    console.log(`Bienvenida enviada a ${mensaje.telefono} (hoy: ${enviadosHoy.total}/${DAILY_LIMIT}).`);
    await dormir(esperaAleatoria());
  } catch (error) {
    console.error("Error enviando mensaje:", error.message);
    await dormir(30000);
  } finally {
    enviando = false;
  }
}

setInterval(cicloEnvio, POLL_SECONDS * 1000);

cliente.initialize();
