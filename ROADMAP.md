# NEXORA ONE — mejoras por bloques

## Bloque 1: seguridad de interacción

- [x] Pausar actualización de la bandeja mientras hay cambios sin enviar.
- [x] Evitar recarga mientras hay un campo enfocado, pestaña oculta o envío pendiente.
- [x] Frenar doble envío de formularios en el navegador, conservando la acción seleccionada.
- [x] Avisar al navegar con cambios sin enviar, sin guardarlos en localStorage.
- [x] Confirmaciones también al enviar un formulario con el teclado.
- [x] Errores de servicios con referencia y sin texto crudo de excepciones.
- [x] Ocultar detalles internos de errores 5xx y autenticación en Telegram.
- [x] Workflow de pruebas Python y JavaScript sin credenciales de producción.
- [x] Bienvenida `/start`, menú con acceso visible al registro gratuito y mensajes que distinguen cuenta faltante, inactiva y servicio caído.

La protección del navegador no garantiza cobros únicos. El workflow de pruebas no bloquea por sí solo el CI/CD de Northflank. La rama vinculada al servicio debe protegerse con el check de test obligatorio y Northflank debe desplegar solo desde esa rama protegida.

## Pendiente

- [x] Descuentos de respuestas con clave idempotente persistente; reintentos tras confirmación perdida no vuelven a cobrar.
- [x] Entregas con resultado ambiguo quedan bloqueadas contra reintento ciego y se concilian manualmente en el panel; Telegram no garantiza entrega exactamente una vez.
- [x] Pruebas de descuento antes y después del commit, replay idempotente y bloqueo de respuesta cuando no se confirma el cobro.
- [x] La bandeja guarda estados de solicitudes y notas de atención con fecha, y muestra registros recientes.
- [x] Separar cada mensaje de la solicitud en un historial estructurado con fecha, autor y tipo; las notas antiguas siguen legibles.
- [x] Unificar entrada por menú, comandos de perfil e historial en el router común sin agregar alias.
- [ ] Completar una pasada con capturas reales en móvil y escritorio.
- [x] Revisión de estilos: quitar el scroll independiente de la barra lateral en escritorio y dejar el desplazamiento en la página.
- [x] Inicio web con solicitudes pendientes, errores recientes y actividad reciente sin IDs de usuarios.
- [x] Salud diferenciada de bot, web y base mediante `/health` y heartbeat periódico.
- [x] La alerta 500 solo aparece para errores de las ultimas 24 horas y el heartbeat guarda sus campos en una transaccion; el historial conserva los registros anteriores.
- [x] Restauración local de respaldo probada en entorno aislado; valida integridad antes de reemplazar y guarda una copia previa.
- [x] Limpieza de historial restringida al fundador, con vista previa, confirmación y backup previo.
- [ ] Acordar cuánto tiempo conservar datos personales; por ahora la limpieza es manual y no se borra información automáticamente.
- [ ] Condicionar despliegues a pruebas exitosas: falta activar la protección de rama en GitHub y desactivar los despliegues directos de Northflank para la rama actual.

No ampliar funciones de búsqueda ni exposición de información personal.
