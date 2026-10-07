# Ronda de mejoras del bot

- [x] Menú por rol: usuario, administrador del grupo y dueño.
- [x] Configuración guiada con vista previa y confirmación de bienvenida, reglas y canal de logs; acceso a protecciones.
- [x] Warn, mute, unmute y unban aceptan ID, respuesta y alias conocido, además del ban existente.
- [x] `/sanciones ID` muestra acciones y retiradas, motivo, administrador y fecha, limitados al grupo.
- [x] TikTok conserva el enlace original en historial y reintentos; obtiene otra URL de descarga si se necesita.
- [x] Reutilización de `file_id` de Telegram, con descarga de respaldo si deja de funcionar.
- [x] Cancelación en consulta TikTok, cola, descarga, procesamiento y envío; el estado de envío permanece visible.
- [x] Daily con cobro atómico; casino con saldo condicionado; transferencias repetidas con el mismo mensaje no se duplican.
- [x] Compras de objetos no acumulables protegidas contra doble cobro; inventario explica efectos y ofrece botones de información.
- [x] `/miscasos` y `/responderticket ID respuesta`; respuestas entregadas quedan guardadas y una entrega fallida no marca sugerencias como respondidas.
- [x] Revalidación de permisos al guardar configuración; canal de logs requiere administración; consultas de casos e historial se limitan al chat.
- [x] Pruebas automáticas de concurrencia, aislamiento entre grupos, moderación, cancelación y reutilización de Telegram.

## Validación real tras el despliegue

- [ ] Confirmar versión activa en Northflank y `/ping`.
- [ ] Descargar un TikTok y repetirlo para verificar el envío reutilizado.
- [ ] Cancelar una descarga en curso y comenzar otra.
- [ ] Probar `/warn ID motivo`, `/mute ID 1m motivo` y sus retiradas con una cuenta de prueba.
- [ ] Abrir `/menu` como usuario y administrador; revisar configuración guiada.
- [ ] Enviar ticket, responderlo y consultar `/miscasos`.

Las pruebas automáticas simulan Telegram; no sustituyen esta validación con el servicio desplegado.
