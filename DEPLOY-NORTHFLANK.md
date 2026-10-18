# Despliegue en Northflank

**Estado:** la migración ya se completó. Northflank es el entorno principal y la rama `deploy/northflank-migration` contiene la configuración usada por los servicios actuales. Este documento queda como guía de configuración y recuperación; no recrees los servicios ni inicialices/importes otra base para una actualización normal.

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
| `NEXORA_OWNER_ID` | ID numérico del dueño principal; define el mismo valor que `OWNER_USER_ID` |
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
| `NEXORA_OWNER_ID` | El mismo ID numérico del dueño, para las funciones administrativas del panel |
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

Configura `BACKUP_CHAT_ID` con el ID del chat privado donde el bot ya guarda las copias. Si lo dejas vacío o en `0`, el bot no enviará copias a Telegram; no existe un ID de respaldo predeterminado en el código.

## Verificar y cambiar el tráfico

1. Comprueba que `/health` de la web responde y que indica `Turso (remoto)`.
2. Arranca el bot en Northflank después de detener el bot de Oracle. Revisa sus logs y consulta `/status` en Telegram; la web debe aparecer `200`, el worker en línea y la base Turso remota.
3. Prueba el panel, `/me`, y una operación de bajo riesgo del bot. Confirma que el panel muestra la información que ya estaba guardada en Turso.
4. Mantén Oracle intacto durante la validación. Para revertir: detén el bot de Northflank y vuelve a iniciar el bot de Oracle. Nunca dejes dos bots haciendo polling a la vez.
5. Después de confirmar estabilidad, conecta los servicios a `main` o configura la rama y despliegue continuo que quieras usar. Northflank puede compilar Dockerfiles desde GitHub en cada cambio de la rama seleccionada.

### Reversión sin recrear servicios ni datos

1. Si el cambio afecta solo al bot, detén temporalmente `nexoraone` para evitar dos procesos de polling mientras restauras una versión anterior.
2. Conserva los servicios y las variables actuales; ambos deben seguir apuntando a la misma base Turso.
3. En Northflank, despliega el último commit estable en los servicios afectados. Oracle ya no forma parte de la ruta de recuperación.
4. Confirma `/status` en Telegram y `/health` de la web. Comprueba que el worker responde y que la base aparece como Turso remoto antes de reanudar cambios.

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

## CI, protecciones de rama y despliegue

El workflow `Tests` valida los cambios, pero no bloquea por sí mismo los despliegues de Northflank. La protección requiere configurar GitHub y ambos servicios:

1. La protección de `deploy/northflank-migration` ya está guardada en GitHub: exige PR y el check `test`. Si se recrea la regla, verifica que seleccione ese check de GitHub Actions. No habilites la inclusión automática de administradores si el dueño necesita una vía de recuperación.
2. En Northflank, `nexoraoneweb` y `nexoraone` tienen CI activo y CD automático desactivado. Mantén ambos servicios apuntando a la misma rama protegida.
3. Flujo normal: crea una rama de cambio → abre un pull request hacia `deploy/northflank-migration` → espera a que `Tests / test` termine en verde → fusiona → comprueba que web y bot están en el mismo commit → despliega manualmente ambos servicios desde ese commit. Mantén una sola réplica del bot.
4. Tras cambiar la rama de producción, actualiza la regla y los dos servicios juntos. No dejes un servicio siguiendo `main` y el otro siguiendo `deploy/northflank-migration`.
5. Para recuperar una versión, elige el mismo commit estable en ambos servicios y confirma `/health` y `/status` después del despliegue.

Si Northflank tiene auto-deploy habilitado, puede empezar a desplegar al recibir un push antes de que GitHub Actions termine; la protección de rama por sí sola no evita despliegues de pushes directos a una rama. Antes de depender de este bloqueo, confirma que el auto-deploy está desactivado en los dos servicios.

### Avisos de GitHub Actions

Los avisos se controlan en [GitHub → Settings → Notifications](https://github.com/settings/notifications), no desde este repositorio. **Only notify for failed workflows** elimina los avisos de ejecuciones exitosas, pero conserva los correos de fallos. Si tampoco quieres recibir esos correos, desactiva las notificaciones de Actions; los resultados siguen visibles en la pestaña **Actions** del repositorio. No uses `continue-on-error` ni suprimas fallos para silenciarlos.

## Documentación oficial

- [Northflank: administrar CI/CD](https://northflank.com/docs/v1/application/release/manage-ci-cd)
- [GitHub: ramas protegidas](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub: administrar avisos de Actions](https://docs.github.com/en/subscriptions-and-notifications/how-tos/managing-github-actions-notifications)
