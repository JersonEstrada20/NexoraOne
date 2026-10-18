# Despliegue en Northflank

## Arquitectura

El proyecto usa dos servicios conectados al mismo repositorio de GitHub:

| Servicio | Dockerfile | Puerto | Réplicas |
| --- | --- | --- | --- |
| `nexoraoneweb` | `/Dockerfile.web` | HTTP 8080 público para el panel y `/health` | 1 |
| `nexoraone` | `/Dockerfile` | Sin puerto público; usa long polling de Telegram | 1 |

Los servicios deben estar en el mismo proyecto de Northflank. El bot llama a la web por la red privada del proyecto (`http://nexoraoneweb:8080`); no necesita que la API interna sea pública. Ambos servicios usan la base Turso ya inicializada. **No ejecutes una inicialización ni importes datos en esa base durante la migración.**

## Antes de empezar: plan y costos

Northflank anuncia el Developer Sandbox con dos servicios, dos tareas programadas y un addon gratis. La cuenta debe registrar un medio de pago para crear recursos, incluso si se elige un plan gratuito. Northflank describe el Sandbox como un entorno para probar y aprender, y dice que no se debe usar para producción. Revisa el plan, recursos y estimación que muestre tu cuenta antes de crear cada servicio; no cambies a Pay-as-you-go ni selecciones recursos con precio. Si la cuenta no muestra claramente ambos servicios a costo cero, pausa aquí.

La aplicación cabe en el límite de dos servicios: bot y web. No crees otro servicio de base de datos; Turso seguirá siendo externo.

## Crear el servicio web

1. Enlaza la cuenta de GitHub y el repositorio `JersonEstrada20/NexoraOne`.
2. Crea el servicio `nexoraoneweb` dentro de un proyecto nuevo o existente. Si creas un proyecto, elige la región disponible más cercana a Santiago: Northflank indica que la región de un proyecto no se puede cambiar después. Selecciona el repositorio y, para la primera validación, la rama `deploy/northflank-migration`.
3. Elige build con Dockerfile, contexto `/` y Dockerfile `/Dockerfile.web`.
4. Configura el puerto `8080` como HTTP público. Northflank generará una URL HTTPS para el panel.
5. Añade las variables privadas de la sección **Variables del servicio web** y despliega una sola réplica.
6. Cuando el despliegue esté listo, abre `/health` en la URL generada. Debe responder y mostrar Turso como almacenamiento remoto. `worker_online` puede seguir en falso hasta arrancar el bot.

## Crear el servicio del bot

1. Crea el servicio `nexoraone` en el mismo proyecto, con el mismo repositorio y rama.
2. Elige build con Dockerfile, contexto `/` y Dockerfile `/Dockerfile`.
3. No agregues puertos públicos. Mantén una réplica para evitar conflictos de long polling de Telegram.
4. Configura las variables privadas de **Variables del servicio bot**.
5. En `NEXORA_API_BASE`, usa `http://nexoraoneweb:8080`. En `NEXORA_PANEL_URL`, usa la URL pública HTTPS del servicio web y añade `/admin/panel`.
6. No arranques simultáneamente este bot y el bot que sigue corriendo en Oracle. Primero detén solo el contenedor/servicio `bot` de Oracle; conserva encendidos la VM y la web de Oracle para poder volver atrás. Después despliega/arranca el bot de Northflank.

## Variables del servicio web

Configura desde Environment/Secrets de Northflank; nunca las guardes en Git.

| Variable | Valor |
| --- | --- |
| `DATABASE_BACKEND` | `turso` |
| `TURSO_DATABASE_URL` | URL actual de la base Turso; cópiala desde la consola de Turso |
| `TURSO_AUTH_TOKEN` | Token nuevo de Turso. Revoca el token anterior y crea uno nuevo antes del despliegue |
| `NEXORA_INTERNAL_API_KEY` | Clave interna actual compartida con el bot |
| `NEXORA_ADMIN_ID` | ID numérico del administrador principal |
| `NEXORA_BOT_NAME` | `NEXORA ONE` |
| `NEXORA_DATA_DIR` | `/data` |
| `NEXORA_PANEL_PUBLIC` | `true` |
| `NEXORA_PANEL_USER` | Usuario de acceso al panel |
| `NEXORA_PANEL_PASSWORD` | Contraseña fuerte del panel |
| `NEXORA_PANEL_SECRET` | Secreto de sesión estable; conserva el actual |
| `BOT_TOKEN` | Token actual del bot, requerido por algunas funciones del panel |
| `PORT` | `8080` |

## Variables del servicio bot

| Variable | Valor |
| --- | --- |
| `BOT_TOKEN` | El mismo token actual del bot |
| `OWNER_USER_ID` | ID numérico del dueño |
| `BACKUP_CHAT_ID` | ID del chat privado de respaldos |
| `DATABASE_BACKEND` | `turso` |
| `TURSO_DATABASE_URL` | URL actual de la base Turso; cópiala desde la consola de Turso |
| `TURSO_AUTH_TOKEN` | Token nuevo de Turso. Revoca el token anterior y crea uno nuevo antes del despliegue |
| `NEXORA_INTERNAL_API_KEY` | La misma clave interna usada por la web |
| `NEXORA_ADMIN_ID` | ID numérico del administrador principal |
| `NEXORA_BOT_NAME` | `NEXORA ONE` |
| `NEXORA_DATA_DIR` | `/data` |
| `NEXORA_API_BASE` | `http://nexoraoneweb:8080` |
| `NEXORA_PANEL_URL` | `https://<dominio-generado-de-la-web>/admin/panel` |

No copies valores desde capturas o logs; escribe los secretos directamente en los campos protegidos de Northflank. No rotes el token de Telegram, credenciales de Turso ni la clave interna durante el cambio.

## Verificar y cambiar el tráfico

1. Comprueba que `/health` de la web responde y que indica `Turso (remoto)`.
2. Arranca el bot en Northflank después de detener el bot de Oracle. Revisa sus logs y consulta `/status` en Telegram; la web debe aparecer `200`, el worker en línea y la base Turso remota.
3. Prueba el panel, `/me`, y una operación de bajo riesgo del bot. Confirma que el panel muestra la información que ya estaba guardada en Turso.
4. Mantén Oracle intacto durante la validación. Para revertir: detén el bot de Northflank y vuelve a iniciar el bot de Oracle. Nunca dejes dos bots haciendo polling a la vez.
5. Después de confirmar estabilidad, conecta los servicios a `main` o configura la rama y despliegue continuo que quieras usar. Northflank puede compilar Dockerfiles desde GitHub en cada cambio de la rama seleccionada.

## Seguridad y recuperación

- `.env`, bases SQLite y llaves privadas no deben subirse al repositorio.
- Los archivos subidos por el panel se guardan en Turso; no dependas del disco efímero del contenedor.
- Mantén los logs privados y no publiques tokens, claves ni variables completas.
- Conserva Oracle como respaldo hasta validar el bot, el panel, la base, los respaldos y las funciones principales en Northflank.
- Consulta el panel de uso y facturación de Northflank después del primer despliegue y antes de cambiar planes.

## Referencias oficiales

- [Precios y Developer Sandbox](https://northflank.com/docs/v1/application/billing/pricing-on-northflank)
- [Crear servicios desde Git y Dockerfile](https://northflank.com/docs/v1/application/build/build-with-a-dockerfile)
- [Puertos internos entre servicios](https://northflank.com/docs/v1/application/network/configure-ports)
