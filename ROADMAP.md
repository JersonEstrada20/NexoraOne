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

La protección del navegador no garantiza cobros únicos. El workflow de pruebas
no bloquea por sí solo el CI/CD de Northflank: falta conectar esa condición.

## Pendiente

- [x] Descuentos de respuestas con clave idempotente persistente; reintentos tras confirmación perdida no vuelven a cobrar.
- [ ] Entrega exactamente una vez y conciliación de envíos ambiguos de Telegram; el envío de Telegram no ofrece clave idempotente.
- [x] Pruebas de descuento antes y después del commit, replay idempotente y bloqueo de respuesta cuando no se confirma el cobro.
- [x] La bandeja guarda estados de solicitudes y notas de atención con fecha, y muestra registros recientes.
- [ ] Separar las respuestas en un historial de conversación estructurado por mensaje y autor.
- [x] Unificar entrada por menú, comandos de perfil e historial en el router común sin agregar alias.
- [ ] Revisar visualmente todos los paneles en móvil y escritorio.
- [x] Inicio web con solicitudes pendientes, errores recientes y actividad reciente sin IDs de usuarios.
- [x] Salud diferenciada de bot, web y base mediante `/health` y heartbeat periódico.
- [x] La alerta 500 solo aparece para errores de las ultimas 24 horas y el heartbeat guarda sus campos en una transaccion; el historial conserva los registros anteriores.
- [x] Restauración local de respaldo probada en entorno aislado; valida integridad antes de reemplazar y guarda una copia previa.
- [x] Limpieza de historial restringida al fundador, con vista previa, confirmación y backup previo.
- [ ] Acordar cuánto tiempo conservar datos personales; por ahora la limpieza es manual y no se borra información automáticamente.
- [ ] Condicionar despliegues a pruebas exitosas.

No ampliar funciones de búsqueda ni exposición de información personal.
