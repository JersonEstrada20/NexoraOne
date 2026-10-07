# NEXORA ONE: persistencia externa sin volumen de pago

Estado: backend implementado e inicializado en Turso. Prueba remota superada; despliegue pendiente.
Existe `scripts/check_turso.py` para comprobar acceso con SELECT 1 sin escribir
ni mostrar secretos. Configurar TURSO_DATABASE_URL y TURSO_AUTH_TOKEN en el
archivo local .env (excluido de Git). No reemplazar las otras variables.
No desplegar suponiendo que las bases locales ya son persistentes.

## Decisiones

- Bot y web permanecen en Northflank; no crear volúmenes de pago.
- Usar el plan gratuito de Turso, sujeto a sus límites actuales.
- Todas las bases comienzan desde cero, autorizado por el dueño.
- Mantener créditos y soles separados, así como los permisos existentes.
- No activar upgrades ni facturación automática.

## Trabajo requerido

- [x] Identificar accesos SQLite: el proyecto tiene 185 coincidencias de
  conexiones/funciones de conexión, síncronas y asíncronas.
- [x] Implementar una capa de acceso remoto con transacciones y errores saneados.
- [x] Unificar tablas sin colisiones; créditos y soles permanecen separados.
- [x] Adaptar inicialización, diagnósticos y exportación remota a SQLite.
- [x] Bloquear restauraciones locales en modo remoto; requieren mantenimiento.
- [x] Guardar imágenes nuevas del panel en la base y conservar file IDs de Telegram.
- [x] Probar escritura, rollback, reconexión, concurrencia idempotente, respaldo y API autenticada.
- [x] Validar contra la base Turso real; datos de prueba retirados.
- [ ] Pruebas de desconexión durante COMMIT y flujos completos Telegram/Northflank.
- [x] Canje real de la ruta probado con fallo simulado antes/después de COMMIT,
  rollback y repetición: sin créditos duplicados (prueba local con libSQL).
- [x] Actualización administrativa de créditos dentro de una transacción;
  error ambiguo pide consultar saldo, sin reintento automático.

Limitación: SQLITE_BUSY puede rechazar una operación concurrente. No se
reintentan automáticamente escrituras ambiguas. La prueba de idempotencia usa
una tabla aislada; no equivale a probar todos los cobros de negocio.

## Paso del dueño

La base Turso ya existe y está inicializada. Para validar el despliegue faltan
localmente NEXORA_API_BASE, NEXORA_INTERNAL_API_KEY, NEXORA_PANEL_USER,
NEXORA_PANEL_PASSWORD y NEXORA_PANEL_SECRET. Guardar sus valores en `.env`
privado (no en el chat) y configurar los correspondientes secretos en Northflank.
`scripts/check_deployment.py` comprueba identidad Telegram y endpoints web sin
arrancar polling ni imprimir credenciales. Suite local: 65 pruebas aprobadas.
No se subieron cambios ni se activaron servicios.
