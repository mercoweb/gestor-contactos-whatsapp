from fastapi import APIRouter, Header, HTTPException, Request

from .. import db, whatsapp
from ..config import DEFAULT_CHANNEL, GOOGLE_FORM_URL, WELCOME_TEMPLATE, APP_TOKEN

router = APIRouter(prefix="/api")


def verificar_token(x_app_token: str = Header(default="")):
    if x_app_token != APP_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido")


def _obtener_o_crear_contacto(telefono, nombre="", email="", ciudad="", grupo="", fecha_ingreso=""):
    tel = whatsapp.normalizar_telefono(telefono)
    if not tel:
        raise ValueError("Teléfono vacío")
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM contactos WHERE telefono = ?", (tel,)).fetchone()
        if row:
            if nombre and not row["nombre"]:
                conn.execute(
                    "UPDATE contactos SET nombre = ?, actualizado_en = ? WHERE id = ?",
                    (nombre, db.now(), row["id"]),
                )
            return dict(row), False
        ahora = db.now()
        conn.execute(
            "INSERT INTO contactos (nombre, telefono, email, ciudad, grupo, fecha_ingreso, estado, creado_en, actualizado_en) "
            "VALUES (?, ?, ?, ?, ?, ?, 'nuevo', ?, ?)",
            (nombre, tel, email, ciudad, grupo, fecha_ingreso, ahora, ahora),
        )
        row = conn.execute("SELECT * FROM contactos WHERE telefono = ?", (tel,)).fetchone()
        return dict(row), True


def _encolar_bienvenida(contacto, canal):
    texto = db.get_setting("welcome_template", WELCOME_TEMPLATE)
    form_url = db.get_setting("google_form_url", GOOGLE_FORM_URL)
    cuerpo = whatsapp.render_plantilla(texto, contacto, form_url)
    mensaje_id = whatsapp.registrar_mensaje(contacto["id"], "bienvenida", canal, cuerpo)
    if canal == "cloud":
        try:
            whatsapp.enviar_cloud_api(contacto["telefono"], cuerpo)
            whatsapp.actualizar_estado_mensaje(mensaje_id, "enviado")
            estado, error = "enviado", ""
        except Exception as exc:
            whatsapp.actualizar_estado_mensaje(mensaje_id, "fallo", str(exc))
            estado, error = "fallo", str(exc)
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE contactos SET bienvenida_enviada = 1, actualizado_en = ? WHERE id = ?",
                (db.now(), contacto["id"]),
            )
        return {"mensaje_id": mensaje_id, "estado": estado, "error": error}
    return {"mensaje_id": mensaje_id, "estado": "pendiente", "error": ""}


@router.get("/health")
def health():
    return {"ok": True}


@router.post("/webhook/whatsapp-join")
def webhook_whatsapp_join(payload: dict, x_app_token: str = Header(default="")):
    verificar_token(x_app_token)
    grupo = payload.get("grupo", "")
    participantes = payload.get("participantes", [])
    canal = payload.get("canal", DEFAULT_CHANNEL)
    resultados = []
    for tel in participantes:
        contacto, es_nuevo = _obtener_o_crear_contacto(tel, grupo=grupo, fecha_ingreso=db.now())
        if contacto.get("bienvenida_enviada"):
            resultados.append({"telefono": tel, "accion": "ya_recibio_bienvenida"})
            continue
        resultado = _encolar_bienvenida(contacto, canal)
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE contactos SET bienvenida_enviada = 1, actualizado_en = ? WHERE id = ?",
                (db.now(), contacto["id"]),
            )
        resultados.append({"telefono": tel, "accion": "bienvenida_" + resultado["estado"], **resultado})
    return {
        "ok": True,
        "nuevos": sum(1 for r in resultados if r.get("accion", "").startswith("bienvenida")),
        "resultados": resultados,
    }


@router.post("/webhook/formulario")
def webhook_formulario(payload: dict, x_app_token: str = Header(default="")):
    verificar_token(x_app_token)
    telefono = payload.get("telefono", "")
    if not telefono:
        raise HTTPException(status_code=400, detail="Falta 'telefono'")
    contacto, _ = _obtener_o_crear_contacto(
        telefono,
        nombre=payload.get("nombre", ""),
        email=payload.get("email", ""),
        ciudad=payload.get("ciudad", ""),
    )
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE contactos SET nombre = COALESCE(NULLIF(?, ''), nombre), "
            "email = COALESCE(NULLIF(?, ''), email), ciudad = COALESCE(NULLIF(?, ''), ciudad), "
            "form_completado = 1, estado = 'formulario_completo', actualizado_en = ? WHERE id = ?",
            (
                payload.get("nombre", ""),
                payload.get("email", ""),
                payload.get("ciudad", ""),
                db.now(),
                contacto["id"],
            ),
        )
    return {"ok": True, "contacto_id": contacto["id"]}


@router.get("/outbox/next")
def outbox_next(x_app_token: str = Header(default="")):
    verificar_token(x_app_token)
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT m.id, m.contacto_id, m.texto, c.telefono, c.nombre "
            "FROM mensajes m JOIN contactos c ON c.id = m.contacto_id "
            "WHERE m.canal = 'bot' AND m.estado = 'pendiente' ORDER BY m.id LIMIT 1"
        ).fetchone()
    if not row:
        return {"mensaje": None}
    return {
        "mensaje": {
            "id": row["id"],
            "telefono": row["telefono"],
            "nombre": row["nombre"],
            "texto": row["texto"],
        }
    }


@router.post("/outbox/{mensaje_id}/resultado")
def outbox_resultado(mensaje_id: int, payload: dict, x_app_token: str = Header(default="")):
    verificar_token(x_app_token)
    estado = payload.get("estado", "enviado")
    whatsapp.actualizar_estado_mensaje(mensaje_id, estado, payload.get("error", ""))
    if estado == "enviado":
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE contactos SET bienvenida_enviada = 1, actualizado_en = ? WHERE id = "
                "(SELECT contacto_id FROM mensajes WHERE id = ?)",
                (db.now(), mensaje_id),
            )
    return {"ok": True}


@router.post("/contactos/{contacto_id}/bienvenida")
def enviar_bienvenida_manual(contacto_id: int, payload: dict, x_app_token: str = Header(default="")):
    verificar_token(x_app_token)
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM contactos WHERE id = ?", (contacto_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    canal = payload.get("canal", DEFAULT_CHANNEL)
    resultado = _encolar_bienvenida(dict(row), canal)
    return {"ok": True, **resultado}


@router.get("/contacto/por-telefono/{telefono}")
def contacto_por_telefono(telefono: str, x_app_token: str = Header(default="")):
    verificar_token(x_app_token)
    tel = whatsapp.normalizar_telefono(telefono)
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM contactos WHERE telefono = ?", (tel,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No encontrado")
    return dict(row)
