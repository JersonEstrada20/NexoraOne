# Plan de mejoras de NEXORA ONE

Checklist viva para la limpieza, auditoría y mejora del bot y del panel. Se actualiza al completar cada cambio. Los elementos sin marcar siguen pendientes.

## Limpieza ya realizada

- [x] Eliminar tres imágenes predeterminadas idénticas y conservar una sola copia.
- [x] Mantener compatibles las URL antiguas de esas imágenes mediante alias.
- [x] Quitar un `import secrets` duplicado.
- [x] Eliminar la URL temporal antigua de Cloudflare como valor predeterminado de Compose.
- [x] Actualizar README y guías para indicar que Northflank es el entorno principal y Oracle es histórico.
- [x] Reemplazar IDs personales por valores neutros en los archivos de configuración de ejemplo.
- [x] Revisar candidatos a eliminación: no se encontraron módulos Python claramente huérfanos; conservar datos, recursos de marca y documentación de recuperación.
- [x] Validar sintaxis de `nexora/web.py`, JSON de ejemplo y formato del diff.

## Avances de mejoras

- [x] Reducir consultas del panel cargando datos solo para las secciones que los muestran.
- [x] Registrar errores del resumen y distinguir “sin actividad” de “no se pudo cargar”.
- [x] En Estadísticas, registrar fallos por fuente y mostrar “—”/“No disponible” en vez de cifras cero engañosas.
- [x] En el resumen y en Sistema, distinguir cuando no fue posible leer los registros de errores.
- [x] Hacer asíncronas las llamadas HTTP directas de `/genkey`, `/redeem`, `/keyslog`, `/keysinfo`, `/setup` y `/setrol`.
- [x] Evitar que las consultas remotas del catálogo en `/cmds` y `/buy` bloqueen el bot; los botones confirman rápido y refrescan el catálogo en segundo plano.
- [x] Evitar consultas síncronas de ajustes remotos al responder `/me` y `/historial`.
- [x] Evitar consultas síncronas de ajustes remotos al responder `/compras`.

## Bot de Telegram

- [x] Revisar comando por comando y botón por botón: confirmar que cada acción conduce al flujo correcto y no duplica otra sección.
- [x] Unificar diseño de los flujos principales: títulos y acciones con emojis, botones agrupados por fila y navegación de regreso en menús, catálogo, compras y herramientas administrativas.
- [x] Mejorar `/start`, `/buy` y `/cmds`: mensajes más claros, accesos ordenados y estados vacíos útiles.
- [x] Restaurar y verificar `/me` para consultar perfil, ID y créditos con usuario o mención cuando corresponda.
- [x] Revisar errores de compras, créditos y solicitudes para mostrar instrucciones seguras de recuperación y evitar reintentos duplicados.
- [x] Sustituir las llamadas HTTP síncronas restantes dentro de todos los manejadores asíncronos por llamadas asíncronas o trabajo fuera del event loop.
- [x] Revisar comandos y respuestas de administración, incluidos comandos configurables y su separación del catálogo público.
- [ ] Hacer una pasada visual real en Telegram de los flujos principales en móvil y escritorio.

## Panel web: visual y experiencia

- [x] Recorrer todas las secciones, formularios, botones y enlaces; corregir acciones que llevan a la misma pantalla por error.
- [x] Mejorar diseño adaptable a móvil: encabezado, navegación, tablas, formularios y botones.
- [x] Unificar estados visuales: cargando, vacío, guardado, error y dato no disponible.
- [x] Mejorar etiquetas, ayuda y confirmación de formularios para que cada acción explique qué cambia.
- [x] Separar la plantilla grande `nexora/templates/admin_panel.html` en componentes o parciales mantenibles.
- [x] Mover estilos en línea a CSS compartido y mantener una presentación consistente.
- [x] Verificar accesibilidad básica: etiquetas de campos, foco de teclado, contraste y nombres claros de botones.

## Panel y backend: rendimiento y confiabilidad

- [x] Cargar solo catálogos, ajustes, paquetes, vistas previas y resumen cuando la sección abierta los necesita.
- [x] Revisar consultas y agregaciones del resumen y estadísticas; paginar listas grandes donde haga falta.
- [x] Reemplazar excepciones de consultas ocultas por registro diagnóstico y estados explícitos, sin confundir error con cero.
- [x] Revisar consistencia de operaciones y referencias de error para que el usuario pueda consultar el resultado antes de repetir una acción; `/errores <referencia>` ya localiza el fallo registrado y orienta a comprobar el estado en el panel.
- [x] Revisar el endpoint de salud y las métricas para distinguir servicio activo, datos disponibles y fallas de base de datos.

## Seguridad y configuración

- [x] Revisar valores de respaldo de IDs de administrador en el código y migrarlos a variables de entorno sin arriesgar el acceso del fundador.
- [x] Confirmar que el servicio del bot en Northflank corre con una instancia y que `/status` indica worker en línea y Turso remoto; Oracle ya fue eliminado por el usuario.
- [x] Confirmar que web y bot tienen iguales los secretos compartidos y la misma base Turso (confirmado por el usuario en Northflank).
- [x] Revisar controles de permisos, CSRF, sesiones y endpoints internos tras los cambios del panel.
- [x] Revisar que ningún secreto, ID personal o URL de despliegue sensible quede en archivos versionados o logs.

## Despliegue y mantenimiento

- [x] Desactivar CD automático en los dos servicios de Northflank; CI sigue activo y los despliegues quedan manuales después de Actions.
- [x] Definir y aplicar las protecciones de rama y la secuencia CI→despliegue; GitHub confirma reglas para `deploy/northflank-migration` y `main`.
- [x] Revisar notificaciones de GitHub Actions: quedó configurado “Failed workflows only”, así no llegan correos de ejecuciones exitosas; los fallos siguen notificándose.
- [x] Documentar recuperación y reversión de Northflank sin recrear servicios ni inicializar otra base.
- [x] Definir y documentar política de retención y copias de seguridad antes de borrar datos productivos.

## Estado de esta auditoría

- Revisión de código y capturas disponibles: realizada como inspección estática.
- Pruebas automatizadas: pendientes; no se ejecutaron en esta tanda.
- Verificación visual en una instancia activa, en móvil y escritorio: pendiente.
- Publicación o despliegue de los cambios de limpieza: pendiente; los cambios siguen locales.
