import csv
import io
import secrets

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import db, whatsapp
from ..config import (
    ADMIN_PASSWORD,
    DEFAULT_CHANNEL,
    GOOGLE_FORM_URL,
    WELCOME_TEMPLATE,
)
from .api import _encolar_bienvenida, _obtener_o_crear_contacto, verificar_token

router = APIRouter()


def contexto_sesion(request: Request):
    return {"sesion": sesion_actual(request) is not None}


templates = Jinja2Templates(directory="app/templates", context_processors=[contexto_sesion])


def sesion_actual(request: Request):
    token = request.cookies.get("sesion", "")
    if not token:
        return None
    with db.get_conn() as conn:
        row = conn.execute("SELECT token FROM sesiones WHERE token = ?", (token,)).fetchone()
    return token if row else None


def requerir_sesion(request: Request):
    if not sesion_actual(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": ""})


@router.post("/login")
def login(request: Request, password: str = Form(default="")):
    if password != ADMIN_PASSWORD:
        return templates.TemplateResponse(request, "login.html", {"error": "Contraseña incorrecta"}, status_code=401)
    token = secrets.token_hex(24)
    with db.get_conn() as conn:
        conn.execute("INSERT INTO sesiones (token, creado_en) VALUES (?, ?)", (token, db.now()))
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("sesion", token, httponly=True, samesite="lax")
    return resp


@router.get("/logout")
def logout(request: Request):
    token = request.cookies.get("sesion", "")
    if token:
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sesiones WHERE token = ?", (token,))
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("sesion")
    return resp


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    requerir_sesion(request)
    with db.get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM contactos").fetchone()["c"]
        con_form = conn.execute("SELECT COUNT(*) c FROM contactos WHERE form_completado = 1").fetchone()["c"]
        bienvenidas = conn.execute(
            "SELECT COUNT(*) c FROM mensajes WHERE tipo = 'bienvenida' AND estado = 'enviado'"
        ).fetchone()["c"]
        pendientes = conn.execute(
            "SELECT COUNT(*) c FROM mensajes WHERE canal = 'bot' AND estado = 'pendiente'"
        ).fetchone()["c"]
        sin_form = total - con_form
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"total": total, "con_form": con_form, "sin_form": sin_form, "bienvenidas": bienvenidas, "pendientes": pendientes},
    )


@router.get("/contactos", response_class=HTMLResponse)
def contactos(
    request: Request,
    q: str = "",
    estado: str = "",
    page: int = 1,
):
    requerir_sesion(request)
    por_pagina = 50
    filtros = []
    params = []
    if q:
        filtros.append("(nombre LIKE ? OR telefono LIKE ? OR email LIKE ? OR ciudad LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like, like]
    if estado:
        filtros.append("estado = ?")
        params.append(estado)
    where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
    with db.get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) c FROM contactos{where}", params).fetchone()["c"]
        filas = conn.execute(
            f"SELECT * FROM contactos{where} ORDER BY creado_en DESC LIMIT ? OFFSET ?",
            params + [por_pagina, (page - 1) * por_pagina],
        ).fetchall()
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    return templates.TemplateResponse(
        request,
        "contactos.html",
        {"filas": filas, "q": q, "estado": estado, "page": page, "paginas": paginas, "total": total},
    )


@router.get("/contactos/nuevo", response_class=HTMLResponse)
def contacto_nuevo_form(request: Request):
    requerir_sesion(request)
    return templates.TemplateResponse(request, "contacto_form.html", {"c": None})


@router.post("/contactos/nuevo")
def contacto_nuevo(
    nombre: str = Form(default=""),
    telefono: str = Form(default=""),
    email: str = Form(default=""),
    ciudad: str = Form(default=""),
    grupo: str = Form(default=""),
    notas: str = Form(default=""),
):
    _obtener_o_crear_contacto(telefono, nombre=nombre, email=email, ciudad=ciudad, grupo=grupo)
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE contactos SET notas = ?, grupo = COALESCE(NULLIF(?, ''), grupo) WHERE telefono = ?",
            (notas, grupo, whatsapp.normalizar_telefono(telefono)),
        )
    return RedirectResponse("/contactos", status_code=303)


@router.get("/contactos/{contacto_id}", response_class=HTMLResponse)
def contacto_editar_form(request: Request, contacto_id: int):
    requerir_sesion(request)
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM contactos WHERE id = ?", (contacto_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No encontrado")
    return templates.TemplateResponse(request, "contacto_form.html", {"c": row})


@router.post("/contactos/{contacto_id}")
def contacto_editar(
    contacto_id: int,
    nombre: str = Form(default=""),
    telefono: str = Form(default=""),
    email: str = Form(default=""),
    ciudad: str = Form(default=""),
    grupo: str = Form(default=""),
    estado: str = Form(default="nuevo"),
    notas: str = Form(default=""),
):
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE contactos SET nombre = ?, telefono = ?, email = ?, ciudad = ?, grupo = ?, estado = ?, notas = ?, actualizado_en = ? "
            "WHERE id = ?",
            (nombre, whatsapp.normalizar_telefono(telefono), email, ciudad, grupo, estado, notas, db.now(), contacto_id),
        )
    return RedirectResponse("/contactos", status_code=303)


@router.post("/contactos/{contacto_id}/eliminar")
def contacto_eliminar(contacto_id: int):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM contactos WHERE id = ?", (contacto_id,))
    return RedirectResponse("/contactos", status_code=303)


@router.post("/contactos/{contacto_id}/bienvenida")
def contacto_bienvenida(contacto_id: int, canal: str = Form(default=DEFAULT_CHANNEL)):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM contactos WHERE id = ?", (contacto_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No encontrado")
    _encolar_bienvenida(dict(row), canal)
    return RedirectResponse(f"/contactos/{contacto_id}", status_code=303)


@router.get("/importar", response_class=HTMLResponse)
def importar_form(request: Request):
    requerir_sesion(request)
    return templates.TemplateResponse(request, "importar.html", {"resultado": None})


@router.post("/importar")
async def importar_csv(request: Request, archivo: UploadFile = File(...)):
    requerir_sesion(request)
    contenido = await archivo.read()
    texto = contenido.decode("utf-8-sig", errors="replace")
    lector = csv.DictReader(io.StringIO(texto))
    creados, actualizados, errores = 0, 0, 0
    for fila in lector:
        fila_limpia = {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()}
        tel = whatsapp.normalizar_telefono(fila_limpia.get("telefono") or fila_limpia.get("teléfono") or fila_limpia.get("phone") or "")
        if not tel:
            errores += 1
            continue
        _, es_nuevo = _obtener_o_crear_contacto(
            tel,
            nombre=fila_limpia.get("nombre", "") or fila_limpia.get("nombre completo", ""),
            email=fila_limpia.get("email", "") or fila_limpia.get("correo", ""),
            ciudad=fila_limpia.get("ciudad", ""),
            grupo=fila_limpia.get("grupo", ""),
            fecha_ingreso=fila_limpia.get("fecha_ingreso", ""),
        )
        if es_nuevo:
            creados += 1
        else:
            actualizados += 1
    resultado = {"creados": creados, "actualizados": actualizados, "errores": errores, "archivo": archivo.filename}
    return templates.TemplateResponse(request, "importar.html", {"resultado": resultado})


@router.get("/mensajes", response_class=HTMLResponse)
def mensajes(request: Request, page: int = 1):
    requerir_sesion(request)
    por_pagina = 50
    with db.get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM mensajes").fetchone()["c"]
        filas = conn.execute(
            "SELECT m.*, c.nombre, c.telefono FROM mensajes m LEFT JOIN contactos c ON c.id = m.contacto_id "
            "ORDER BY m.id DESC LIMIT ? OFFSET ?",
            (por_pagina, (page - 1) * por_pagina),
        ).fetchall()
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    return templates.TemplateResponse(
        request, "mensajes.html", {"filas": filas, "page": page, "paginas": paginas, "total": total}
    )


@router.get("/configuracion", response_class=HTMLResponse)
def configuracion_form(request: Request):
    requerir_sesion(request)
    valores = {
        "welcome_template": db.get_setting("welcome_template", WELCOME_TEMPLATE),
        "google_form_url": db.get_setting("google_form_url", GOOGLE_FORM_URL),
    }
    return templates.TemplateResponse(request, "configuracion.html", {"val": valores})


@router.post("/configuracion")
def configuracion_guardar(
    welcome_template: str = Form(default=""),
    google_form_url: str = Form(default=""),
):
    db.set_setting("welcome_template", welcome_template)
    db.set_setting("google_form_url", google_form_url)
    return RedirectResponse("/configuracion", status_code=303)
