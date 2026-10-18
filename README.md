# NEXORA ONE

El inventario inicial de datos, las medidas vigentes y los pasos pendientes para fijar retención están en [DATA-RETENTION.md](DATA-RETENTION.md). No se ejecuta una purga automática general.

Bot de Telegram **@NexoraOneRoBot** y panel web para administrar usuarios, solicitudes, créditos y catálogo. Incluye moderación de grupos, herramientas de comunidad, automatizaciones y descargas multimedia.

## Estado del despliegue

La migración a Northflank está en preparación. **Hasta completar el corte, Oracle Cloud sigue siendo producción y el bot de Oracle no se debe apagar.** La arquitectura destino usa dos servicios del repositorio de GitHub:

- **Bot**: servicio `nexoraone`, ejecuta `/Dockerfile` y usa long polling de Telegram; debe tener una sola réplica.
- **Web**: servicio `nexoraoneweb`, ejecuta `/Dockerfile.web`, sirve el panel y la API por HTTP 8080.
- **Base de datos**: bot y web usan la misma base remota existente de Turso. No se importan datos ni se crea una segunda base.
- **Acceso al panel**: la web obtiene un dominio HTTPS de Northflank; el bot usa la dirección privada del servicio web.

Sigue [DEPLOY-NORTHFLANK.md](DEPLOY-NORTHFLANK.md) para la migración, validación y reversión. [DEPLOY-ORACLE.md](DEPLOY-ORACLE.md) queda como guía de respaldo. No compartas archivos `.env`, tokens de Telegram, tokens de Turso ni claves internas.

## Funciones

- Moderación: enlaces, flood, palabras bloqueadas, captcha, advertencias, silencios, expulsiones, reportes y registros.
- Administración: reglas, bienvenida, roles, notas, comandos, solicitudes y estadísticas. Cada solicitud conserva una línea de tiempo por mensaje con fecha, autor y tipo; las notas históricas anteriores siguen disponibles.
- Si Telegram no confirma una entrega, la solicitud queda marcada para revisión. Comprueba el chat del usuario antes de confirmar que llegó o permitir un reintento desde el panel.
- Comunidad: sorteos, encuestas, niveles, mensajes programados y herramientas para grupos.
- Economía: perfiles, créditos, recompensas y compras. Los créditos y los saldos en soles se mantienen separados.
- Multimedia: descargas de TikTok, Instagram, YouTube y Facebook, según disponibilidad de cada plataforma.
- Panel web para administrar catálogo, solicitudes, cuentas, claves y configuración.

`/start` da la bienvenida y abre el menú; `/menu` vuelve a mostrar las categorías. Para Consultas y Servicios, la cuenta se crea gratis con `/register`. Si una cuenta está desactivada, el bot indica el contacto oficial; si la web no responde, pide intentarlo más tarde en vez de registrarse otra vez. Las funciones disponibles dependen de los permisos del bot, la configuración del grupo y los límites de cada plataforma.

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

La base productiva ya está inicializada. **No vuelvas a inicializar ni importes otra base durante la migración.** Los dos servicios de Northflank deben usar la misma URL y token de Turso que la producción actual.

## Verificación

La suite local automatizada se ejecuta con:

```powershell
python -m unittest discover -s tests -q
node --test tests/panel-safety.test.cjs
```

El flujo y el orden seguro del cambio están descritos en [DEPLOY-NORTHFLANK.md](DEPLOY-NORTHFLANK.md). `/health` comprueba la web y el backend; `worker_online:true` confirma que el bot está enviando heartbeats.

## Seguridad y datos

- Los secretos van en el gestor de secretos del proveedor de despliegue o en el `.env` local protegido, siempre fuera de Git.
- No subas bases locales ni datos de usuarios al repositorio.
- Mantén una sola instancia de bot para evitar conflictos de long polling.
- Los archivos `.db` locales no son la fuente de datos de producción cuando `DATABASE_BACKEND=turso`.
- La eliminación manual de historiales personales es solo para el fundador y exige vista previa, confirmación y respaldo previo. El historial de descargas se purga a los 30 días; el detalle y las limitaciones están en [DATA-RETENTION.md](DATA-RETENTION.md).
- La restauración web está limitada a bases SQLite locales; valida integridad y guarda una copia de seguridad antes de reemplazar archivos.
- La política de retención inicial está en [DATA-RETENTION.md](DATA-RETENTION.md); las recomendaciones de respaldo están en [DEPLOY-NORTHFLANK.md](DEPLOY-NORTHFLANK.md).
