# Operación en Northflank

## Arquitectura en producción

El despliegue existente tiene dos servicios conectados al mismo repositorio y rama `main`:

| Servicio | Dockerfile | Función | Red |
| --- | --- | --- | --- |
| `nexoraone` | `/Dockerfile` | Bot de Telegram con long polling | Sin puerto público; una instancia |
| `nexoraoneweb` | `/Dockerfile.web` | Panel, API y healthcheck | Puerto HTTP `8080`; endpoint `/health` |

Ambos servicios usan la misma base Turso. El bot envía un heartbeat cada minuto al endpoint interno de la web. Para confirmar conexión, consulta `/health`: `web_online` y `worker_online` deben ser `true`, y `data_volume` debe indicar `Turso (remoto)`.

## Variables y secretos

Configura los secretos desde la página **Environment** de cada servicio. No los pegues en chats ni los guardes en Git.

### En ambos servicios

- `DATABASE_BACKEND=turso`
- `TURSO_DATABASE_URL`: URL de la misma base Turso
- `TURSO_AUTH_TOKEN`: token de acceso de esa base
- `NEXORA_INTERNAL_API_KEY`: misma clave aleatoria en web y bot
- `NEXORA_ADMIN_ID=7454664711`
- `NEXORA_BOT_NAME=NEXORA ONE`
- `BOT_TOKEN`: token actual de `@NexoraOneRoBot`

### Solo en el bot `nexoraone`

- `NEXORA_API_BASE`: URL HTTPS completa de `nexoraoneweb`, por ejemplo `https://<host>.code.run`
- `BACKUP_CHAT_ID`: chat privado autorizado para recibir respaldos
- `NEXORA_DATA_DIR`: directorio temporal local; los datos productivos se guardan en Turso

### Solo en la web `nexoraoneweb`

- `NEXORA_PANEL_USER`
- `NEXORA_PANEL_PASSWORD`
- `NEXORA_PANEL_SECRET`: secreto estable para firmar sesiones; no lo cambies en cada deploy
- `NEXORA_PANEL_PUBLIC=true` si el login del panel debe estar disponible públicamente
- `NEXORA_DATA_DIR=/data`

La web también puede usar `BOT_TOKEN` para algunas integraciones de Telegram. Debe ser el token actual del mismo bot.

## Actualizar la aplicación

1. Envía los cambios a `main` en GitHub; Northflank debe iniciar un build desde ese commit.
2. Comprueba que el build de ambos servicios termina correctamente y que el bot sigue en una sola instancia.
3. Revisa los logs sin copiar tokens ni claves.
4. Consulta `/health`. La fecha `last_worker_seen` debe actualizarse y `worker_online` debe quedar en `true`.
5. Confirma `/status` en Telegram y realiza una comprobación funcional de bajo riesgo.

Un build verde confirma que la imagen se creó; no confirma por sí solo la conexión de los dos servicios o el funcionamiento de cada comando.

## Inicializar una base Turso nueva

La base de producción ya existe y está inicializada. **No ejecutes estos pasos sobre la base actual ni importes datos antiguos.** Para una base nueva y vacía:

1. Configura `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN` en el entorno local privado.
2. Activa el backend remoto solo para el proceso de inicialización y ejecuta:

   ```powershell
   $env:DATABASE_BACKEND = "turso"
   .\.venv\Scripts\python.exe scripts/init_turso.py --initialize
   ```

3. Espera los mensajes de inicialización completa. Si el proceso falla, no despliegues contra esa base hasta revisar la causa.
4. Verifica la conexión de lectura con `python scripts/check_turso.py` y configura los mismos secretos en los dos servicios.

No compartas ni incluyas en capturas el token de Turso. Al terminar, cierra la terminal o elimina la variable temporal de entorno.

## Respaldo y recuperación

Los respaldos unificados se exportan a SQLite y se envían al chat privado configurado. Antes de cualquier restauración, pausa bot y web para evitar escrituras concurrentes. Comprueba el respaldo fuera de producción antes de restaurar; no uses archivos SQLite locales como si fueran una copia actual de Turso.

Turso puede rechazar escrituras concurrentes con `SQLITE_BUSY`. Una operación con resultado ambiguo debe verificarse antes de repetirse, especialmente si implica créditos, saldos o entregas.

## Costos y operación

Revisa los planes, instancias y cargos que muestra tu cuenta de Northflank antes de cambiar recursos. Mantén una instancia del bot y desactiva o elimina servicios que ya no uses desde Northflank; borrar archivos locales no detiene recursos alojados.
