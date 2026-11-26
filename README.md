# 📱 Gestor de Contactos WhatsApp

Aplicación independiente para administrar +800 contactos de un grupo de WhatsApp:

- **Panel de administración web** con base de datos SQLite (sin instalar gestores de BD).
- **Importación de contactos** desde CSV/Excel.
- **Bienvenida automática** cuando entra alguien nuevo al grupo (vía bot) o con un clic desde el panel.
- **Webhook para Google Forms**: los contactos reciben un link por WhatsApp, llenan el formulario y los datos caen solos en la base de datos.
- **Dos canales de envío**: bot con whatsapp-web.js (automático, con límites anti-bloqueo) y WhatsApp Cloud API oficial de Meta (opcional, sin riesgo).

## Requisitos

- Python 3.10 o superior
- Node.js 18 o superior (solo para el bot de detección de grupo)
- Para el canal "cloud": una cuenta en [Meta for Developers](https://developers.facebook.com/) con WhatsApp Cloud API

## Instalación rápida

### 1. Aplicación principal (panel + base de datos)

```bash
cd gestor-contactos-whatsapp
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

Edita `.env` y cambia **obligatoriamente** `APP_TOKEN` y `ADMIN_PASSWORD`.

Arranca la app:

```bash
python run.py
```

Abre http://localhost:8000 e inicia sesión con tu `ADMIN_PASSWORD`.

### 2. Importar tus 800+ contactos

1. Exporta los contactos del grupo a CSV (columnas: `nombre`, `telefono`, `email`, `ciudad`, `grupo`, `fecha_ingreso`).
2. Entra a **Importar CSV** en el panel y sube el archivo.
3. El teléfono debe llevar código de país sin `+` ni espacios (ej. `5491122334455`).

### 3. Bot de bienvenida automática (opcional, canal "bot")

```bash
cd wa_bot
npm install
cp .env.example .env        # Windows: copy .env.example .env
npm start
```

Escanea el QR con tu teléfono (WhatsApp → Dispositivos vinculados). El bot:

- Detecta con el evento `group_join` cuando alguien entra al grupo configurado.
- Registra al nuevo miembro en la base de datos automáticamente.
- Encola la bienvenida y la envía con **retardo aleatorio (90–300 s)** y **límite diario (150)** para reducir el riesgo de bloqueo.

⚠️ **Advertencia**: whatsapp-web.js no es oficial de WhatsApp. Usarlo automatiza tu número contra sus términos de servicio y con 800 contactos existe riesgo real de bloqueo. Úsalo con un número de negocio, calienta el número gradualmente y no lo uses para spam. Si quieres cero riesgo, usa el canal "cloud".

### 4. WhatsApp Cloud API (opcional, canal "cloud")

1. Crea una app en [Meta for Developers](https://developers.facebook.com/) y agrega el producto **WhatsApp**.
2. Copia tu `Phone number ID` y el token de acceso en `.env` (`CLOUD_API_PHONE_ID`, `CLOUD_API_TOKEN`).
3. Pon `DEFAULT_CHANNEL=cloud` en `.env` (o elige el canal en cada envío desde el panel).
4. Con este canal las bienvenidas se envían por la API oficial: sin riesgo de bloqueo. Las plantillas fuera de la ventana de 24 h requieren una plantilla aprobada por Meta.

### 5. Formulario con Google Forms

1. Crea un Google Form con: **nombre completo**, **email**, **ciudad** y **teléfono**.
2. Copia el link del formulario y pégalo en **Configuración** del panel. Ese link se inserta automáticamente en la bienvenida donde va `{link}`.
3. En el formulario abre **Extensiones → Apps Script**, pega el contenido de [`google_appscript/codigo.gs`](google_appscript/codigo.gs) y reemplaza:
   - `URL_DE_TU_APP` → la URL pública donde corre esta app.
   - `TOKEN_SECRETO_DE_LA_APP` → el `APP_TOKEN` de tu `.env`.
4. Crea un activador: función `alEnviarFormulario`, tipo "Al enviarse el formulario".
5. Cada respuesta actualizará el contacto en la base de datos (marca ✅ formulario completo).

### 6. Acceso desde internet (para webhooks)

Google Forms y Cloud API necesitan alcanzar tu aplicación:

- **Local rápido**: usa un túnel como `cloudflared tunnel --url http://localhost:8000` y pon esa URL en Apps Script.
- **Producción**: despliega en un VPS (ej. con `uvicorn` detrás de nginx) o un servicio como Railway/Render/Fly.io con SQLite persistente.

## Arquitectura

```
Google Form ──(Apps Script webhook)──▶ /api/webhook/formulario ──▶ SQLite
WhatsApp grupo ──(bot Node: group_join)──▶ /api/webhook/whatsapp-join ──▶ SQLite + cola
Panel admin (FastAPI + Jinja2) ◀── lee/escribe ──▶ SQLite
Bot Node ◀── poll /api/outbox/next ──▶ envía mensajes con retardos anti-bloqueo
Cloud API (Meta) ◀── envío directo desde Python (canal "cloud")
```

## Estructura del proyecto

```
├── app/                  # Aplicación Python (FastAPI + SQLite)
│   ├── main.py           # Punto de entrada de la app web
│   ├── db.py             # Esquema y acceso a la base de datos
│   ├── whatsapp.py       # Envío Cloud API + utilidades de teléfono
│   ├── routers/admin.py  # Panel de administración (páginas)
│   ├── routers/api.py    # API JSON (webhooks, outbox, envíos)
│   └── templates/        # Páginas HTML del panel
├── wa_bot/               # Bot Node.js (whatsapp-web.js)
│   └── bot.js            # Detección de miembros + envío de bienvenidas
├── google_appscript/
│   └── codigo.gs         # Script para conectar Google Forms con la app
├── requirements.txt
└── run.py
```

## Seguridad

- Todas las rutas `/api/*` exigen el header `X-App-Token` (el `APP_TOKEN` de `.env`).
- El panel pide contraseña (`ADMIN_PASSWORD`) y usa cookie de sesión.
- No compartas el `.env`; ya está excluido del repositorio vía `.gitignore`.
