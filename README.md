# NEXORA ONE

Bot de Telegram **@NexoraOneRoBot** y panel web para administrar usuarios, solicitudes, créditos y catálogo. Incluye moderación de grupos, herramientas de comunidad, automatizaciones y descargas multimedia.

## Estado del despliegue

La producción está separada en dos servicios de Northflank:

- **Bot**: servicio `nexoraone`, ejecuta `Dockerfile` y usa long polling de Telegram. Debe mantenerse en una instancia y no necesita puerto público.
- **Web**: servicio `nexoraoneweb`, ejecuta `Dockerfile.web`, publica HTTP en el puerto `8080` y ofrece el panel y la API.
- **Base de datos**: ambos servicios usan la misma base remota de Turso. El endpoint `/health` informa el estado de la web, la base y el heartbeat del bot.

La guía de variables, builds y recuperación está en [DEPLOY-NORTHFLANK.md](DEPLOY-NORTHFLANK.md). No compartas archivos `.env`, tokens de Telegram, tokens de Turso ni claves internas.

## Funciones

- Moderación: enlaces, flood, palabras bloqueadas, captcha, advertencias, silencios, expulsiones, reportes y registros.
- Administración: reglas, bienvenida, roles, notas, comandos, solicitudes y estadísticas.
- Comunidad: sorteos, encuestas, niveles, mensajes programados y herramientas para grupos.
- Economía: perfiles, créditos, recompensas y compras. Los créditos y los saldos en soles se mantienen separados.
- Multimedia: descargas de TikTok, Instagram, YouTube y Facebook, según disponibilidad de cada plataforma.
- Panel web para administrar catálogo, solicitudes, cuentas, claves y configuración.

Los comandos y accesos principales se organizan con `/menu`. Las funciones disponibles dependen de los permisos del bot, la configuración del grupo y los límites de cada plataforma.

## Ejecución local

Requisitos: Python 3.12, FFmpeg y Node.js solo si vas a ejecutar la verificación del panel.

1. Crea y activa un entorno virtual:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Instala dependencias y prepara la configuración:

   ```powershell
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. En `.env`, configura como mínimo `BOT_TOKEN`. Para desarrollo local, deja `DATABASE_BACKEND=sqlite`; el archivo del bot se crea en `app/data/bot.db`.

4. Inicia el bot:

   ```powershell
   python -m app.main
   ```

Para ejecutar la web localmente, configura `NEXORA_PANEL_SECRET`, `NEXORA_PANEL_USER` y `NEXORA_PANEL_PASSWORD`, además de las variables de conexión entre servicios si vas a probar la API. La guía de producción explica las variables con más detalle.

## Turso y persistencia

En producción, bot y web deben tener `DATABASE_BACKEND=turso` y los mismos `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN`. La web también requiere una `NEXORA_PANEL_SECRET` estable. El bot necesita la URL HTTPS de la web en `NEXORA_API_BASE` y la misma `NEXORA_INTERNAL_API_KEY` configurada en la web.

La base productiva ya está inicializada. **No vuelvas a inicializar ni importes otra base sobre la producción.** Para crear una base Turso nueva, sigue la sección de inicialización en [DEPLOY-NORTHFLANK.md](DEPLOY-NORTHFLANK.md).

## Verificación

La suite local automatizada se ejecuta con:

```powershell
python -m unittest discover -s tests -q
node --test tests/panel-safety.test.cjs
```

El flujo de despliegue también está descrito en [DEPLOY-NORTHFLANK.md](DEPLOY-NORTHFLANK.md). `/health` comprueba la web y el backend; `worker_online:true` confirma que el bot está enviando heartbeats.

## Seguridad y datos

- Los secretos van en variables protegidas de Northflank o en el `.env` local, que Git ignora.
- No subas bases locales ni datos de usuarios al repositorio.
- Mantén una sola instancia de bot para evitar conflictos de long polling.
- Los archivos `.db` locales no son la fuente de datos de producción cuando `DATABASE_BACKEND=turso`.
