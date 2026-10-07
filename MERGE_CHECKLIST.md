# NEXORA ONE — integración y despliegue

- [x] Marca visible NEXORA ONE y bot @NexoraOneRoBot.
- [x] Dueño @PeruDoxer (7454664711); contacto oficial @OficialNexora (7151644287), sin elevar permisos.

- [x] Importación selectiva, sin historial Git ni secretos del ZIP.
- [x] Inicio limpio: eliminadas las cinco bases importadas; originales conservados solo en el ZIP de origen.
- [x] Un receptor de Telegram; web Flask en servicio separado.
- [x] Entradas `/register`, `/perfil`, `/paneladmin`, `/historial` y `/backup`.
- [x] Créditos separados de soles; no convertir ni sumar saldos.
- [x] `/bang` y `/unbang` para grupos; `/ban` y `/unban` para acceso al bot.
- [x] Confirmación de `/bangg` y `/unbangg`, resultados por grupo y avisos.
- [x] Pruebas locales: regresiones, comandos únicos, bloqueo persistente y API web aislada.
- [ ] Prueba integral con la web desplegada y Telegram real.
- [x] No importar bases antiguas: el servicio creará las tablas al iniciar.
- [ ] Configurar URL, clave interna y acceso al panel web.
- [ ] Prueba privada de Telegram y despliegue final.

## Despliegue pendiente

El bot usa `Dockerfile`; el servicio web usa `Dockerfile.web`.
En ambos configurar la misma `NEXORA_INTERNAL_API_KEY` (secreto aleatorio).
En el bot: `BOT_TOKEN`, `NEXORA_API_BASE` con la URL HTTPS del servicio web,
`NEXORA_ADMIN_ID=7454664711`, `NEXORA_DATA_DIR` en un volumen persistente.
En la web: `BOT_TOKEN`, `NEXORA_ADMIN_ID=7454664711`, `NEXORA_DATA_DIR=/data`,
`NEXORA_PANEL_USER`, `NEXORA_PANEL_PASSWORD`, `NEXORA_PANEL_SECRET` y
`NEXORA_PANEL_PUBLIC=true` si se necesita acceso público al login.
Montar un volumen persistente vacío en `/data`. Las tablas se crearán al
primer arranque, sin usuarios, créditos ni historiales importados. El sistema
puede crear su configuración inicial y la cuenta del dueño automáticamente.
No publicar bases ni secretos en Git.
El bot conserva además su volumen existente para `DB_PATH`.

El ban global solo puede alcanzar grupos conocidos donde Telegram permita
restringir miembros. No puede expulsar propietarios/administradores. Los fallos
se enumeran; desbanear no vuelve a incorporar al usuario al grupo.
