import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS contactos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL DEFAULT '',
    telefono TEXT NOT NULL UNIQUE,
    email TEXT DEFAULT '',
    ciudad TEXT DEFAULT '',
    grupo TEXT DEFAULT '',
    fecha_ingreso TEXT DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'nuevo',
    bienvenida_enviada INTEGER NOT NULL DEFAULT 0,
    form_completado INTEGER NOT NULL DEFAULT 0,
    notas TEXT DEFAULT '',
    creado_en TEXT NOT NULL,
    actualizado_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mensajes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contacto_id INTEGER NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'bienvenida',
    canal TEXT NOT NULL DEFAULT 'bot',
    texto TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'pendiente',
    error TEXT DEFAULT '',
    creado_en TEXT NOT NULL,
    enviado_en TEXT
);

CREATE TABLE IF NOT EXISTS configuracion (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sesiones (
    token TEXT PRIMARY KEY,
    creado_en TEXT NOT NULL
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    path = DB_PATH.rsplit("/", 1)[0]
    os.makedirs(path, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def now():
    return datetime.now().isoformat(timespec="seconds")


def get_setting(key, default=""):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT valor FROM configuracion WHERE clave = ?", (key,)
        ).fetchone()
    return row["valor"] if row else default


def set_setting(key, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (key, value),
        )

