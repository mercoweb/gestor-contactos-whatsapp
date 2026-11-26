import re

import requests

from . import db
from .config import (
    CLOUD_API_PHONE_ID,
    CLOUD_API_TOKEN,
    CLOUD_API_VERSION,
)


def normalizar_telefono(telefono):
    digitos = re.sub(r"\D", "", str(telefono))
    return digitos


def render_plantilla(texto, contacto, link=""):
    valores = {
        "nombre": contacto["nombre"] or "",
        "telefono": contacto["telefono"] or "",
        "email": contacto["email"] or "",
        "ciudad": contacto["ciudad"] or "",
        "link": link,
    }
    resultado = texto
    for clave, valor in valores.items():
        resultado = resultado.replace("{" + clave + "}", valor)
    return resultado


def registrar_mensaje(contacto_id, tipo, canal, texto, estado="pendiente", error=""):
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO mensajes (contacto_id, tipo, canal, texto, estado, error, creado_en) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (contacto_id, tipo, canal, texto, estado, error, db.now()),
        )
        return cur.lastrowid


def actualizar_estado_mensaje(mensaje_id, estado, error=""):
    enviado = db.now() if estado == "enviado" else None
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE mensajes SET estado = ?, error = ?, enviado_en = COALESCE(?, enviado_en) WHERE id = ?",
            (estado, error, enviado, mensaje_id),
        )


def enviar_cloud_api(telefono, texto):
    if not CLOUD_API_PHONE_ID or not CLOUD_API_TOKEN:
        raise RuntimeError("Cloud API no configurada: faltan CLOUD_API_PHONE_ID y CLOUD_API_TOKEN")
    tel = normalizar_telefono(telefono)
    url = f"https://graph.facebook.com/{CLOUD_API_VERSION}/{CLOUD_API_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": tel,
        "type": "text",
        "text": {"preview_url": True, "body": texto},
    }
    headers = {"Authorization": f"Bearer {CLOUD_API_TOKEN}"}
    resp = requests.post(url, json=payload, headers=headers, timeout=20)
    if resp.status_code >= 400:
        raise RuntimeError(f"Cloud API error {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def enviar_por_canal(canal, telefono, texto):
    if canal == "cloud":
        return enviar_cloud_api(telefono, texto)
    return {"enviado_a_cola": True}
