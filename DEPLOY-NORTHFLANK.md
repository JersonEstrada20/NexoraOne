# NEXORA ONE — montaje de bot y web

> CONFIGURACIÓN TURSO:
> NO crear volúmenes de pago. Bot y web deben configurar `DATABASE_BACKEND=turso`,
> la misma `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN` como secretos de ejecución.
> Conservar `BOT_TOKEN` nuevo y la misma `NEXORA_INTERNAL_API_KEY` en ambos.
> La web requiere `NEXORA_PANEL_SECRET` estable además de usuario y contraseña.
> La base remota nueva ya se inicializó; no importar bases antiguas ni borrar datos.
> Los `.db` locales NO son la fuente de datos al usar Turso. Imágenes nuevas del
> panel se guardan en la base (máximo 512 KB). Créditos y soles siguen separados.
> Respaldos unificados se exportan a SQLite y envían al canal privado del dueño.
> Restaurar requiere mantenimiento con ambos servicios pausados; los botones de
> restauración de archivos locales quedan bloqueados para evitar un éxito falso.
> No desplegar hasta que `scripts/test_turso_live.py --write-test` termine bien.
> Una escritura concurrente puede ser rechazada por SQLITE_BUSY; no reintentar
> cobros ambiguos sin comprobar el estado.

## Actualizaciones del despliegue existente

Bot y web ya están creados. No recrear servicios ni inicializar o vaciar la base
para una actualización. Conservar sus variables de entorno.

1. Ejecutar las pruebas con `DATABASE_BACKEND=sqlite` para aislarlas de producción.
2. Ejecutar `python scripts/check_deployment.py` (comprobación de solo lectura).
3. Subir el commit y comprobar que ambos servicios construyan y desplieguen ese
   commit; si CI/CD está desactivado, iniciar Build y después Deploy manualmente.
4. Mantener una sola instancia del bot. Comprobar `/status`, una descarga real y
   la entrega de una respuesta como mensaje nuevo en Telegram.
5. Revisar los logs. Un HTTP 200 de la web no confirma la versión del bot.

Revisar los recursos, límites y coste mostrados por Northflank antes de crear servicios o volúmenes. Este proyecto usa dos servicios del mismo repositorio y un solo receptor de Telegram.

## Web (servicio separado)

- Contexto `/`, Dockerfile `/Dockerfile.web`, una instancia, puerto HTTP público `8080`.
- Sin volumen. `NEXORA_DATA_DIR=/data` solo almacena archivos temporales.
- `NEXORA_ADMIN_ID=7454664711`, `NEXORA_BOT_NAME=NEXORA ONE`, `NEXORA_PANEL_PUBLIC=true`.
- Secretos: `BOT_TOKEN`, `NEXORA_INTERNAL_API_KEY`, `NEXORA_PANEL_USER`, `NEXORA_PANEL_PASSWORD`, `NEXORA_PANEL_SECRET`.
- Health check: `/health` en puerto `8080`.
- Las bases de servicios se crean nuevas. No importar el ZIP antiguo.

## Conexión entre servicios

En el bot configurar `NEXORA_API_BASE` con la URL HTTPS de la web y la misma
`NEXORA_INTERNAL_API_KEY`. Usar `NEXORA_ADMIN_ID=7454664711`.
Ambos servicios deben apuntar a la MISMA base Turso ya inicializada.

El token debe corresponder a **@NexoraOneRoBot**. Si es un bot nuevo, añadirlo
como administrador a grupos y al canal privado de respaldos.
Dueño: **@PeruDoxer (7454664711)**. Cuenta oficial de contacto:
**@OficialNexora (7151644287)**, sin permisos automáticos de dueño.
Canal público oficial: **@NexoraOneOficial**. No sustituye al canal privado
de respaldos `-1004334720154`.
@NexoraOneRoBot es un bot nuevo: configurar su token nuevo como secreto en
ambos servicios. Conservar los datos actuales antes de pausar o reemplazar
el despliegue anterior; no eliminar el servicio ni su volumen sin respaldo.

## Preparación

1. Sube esta carpeta a un repositorio privado de GitHub. No subas `.env` ni `app/data/bot.db`.
2. Crea una cuenta en https://northflank.com y entra con GitHub.
3. Selecciona el proyecto y revisa el plan disponible en tu cuenta.

## Servicio

1. Selecciona **Create service → Combined service**.
2. Conecta el repositorio y la rama principal.
3. En Build type selecciona **Dockerfile** y usa `/Dockerfile`.
4. Elige los recursos adecuados y deja una sola instancia.
5. No necesitas puerto público: Telegram funciona mediante long polling.
6. En variables/secretos agrega:
   - `BOT_TOKEN`: token válido entregado por BotFather.
   - `DATABASE_BACKEND`: `turso`.
   - `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN`: los mismos que en la web.
   - `DB_PATH`: `app/data/bot.db` (ruta de trabajo, no almacenamiento remoto).
   - `BACKUP_CHAT_ID`: ya queda configurado por defecto como `-1004334720154`; puedes agregarlo también como secreto para dejarlo visible en la configuración.
7. Despliega y revisa los logs. Debe aparecer `Bot iniciado correctamente...`.

## Persistencia

Los datos se escriben directamente en Turso, sin volumen. Las exportaciones
locales son temporales y el bot las envía al canal privado. Si omites
`DATABASE_BACKEND=turso`, se usa SQLite local y los datos NO serán persistentes.

No agregues el token directamente al repositorio. Northflank debe guardarlo como secreto de ejecución.
