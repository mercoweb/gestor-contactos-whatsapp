from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routers import admin, api

init_db()

app = FastAPI(title="Gestor de Contactos WhatsApp", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(api.router)
app.include_router(admin.router)
