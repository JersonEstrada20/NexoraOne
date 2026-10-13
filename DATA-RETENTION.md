# Política provisional de datos y retención

**Estado:** inventario inicial; plazos sujetos a aprobación del responsable del proyecto.  
**Ámbito:** datos guardados por el bot y el panel en Turso o SQLite local.

Esta política no activa ni autoriza una purga general. Los datos personales se conservan solo mientras sean necesarios para la finalidad informada; luego deben suprimirse o anonimizarse, salvo una razón legal válida para conservarlos. La Ley chilena 21.719 entra en vigencia el 1 de diciembre de 2026. Este documento es una guía operativa, no asesoría legal.

## Inventario y tratamiento actual

| Grupo | Datos y finalidad | Retención provisional | Automatización actual |
| --- | --- | --- | --- |
| Historial de descargas | ID de Telegram, nombre/medio y fecha para mostrar el historial personal y limitar abuso | 30 días | Sí; purga horaria en `media_cleanup_loop` |
| Archivos temporales de descarga | Archivos de trabajo locales | 1 hora desde última modificación | Sí; limpieza horaria |
| Caché de medios | Referencias y metadatos para reutilizar descargas | Hasta que venza o se recorte la caché | Sí; límites de caché existentes |
| Solicitudes y respuestas de soporte | Identificadores Telegram, mensajes, estados y fechas para atender/confirmar solicitudes | Mantener mientras esté abierta; al cerrar, revisar y borrar o anonimizar cuando ya no haga falta para soporte. No se fija aún un número de días | No hay purga automática general |
| Tickets, reportes, sugerencias y moderación | IDs, motivos, mensajes/reportes y decisiones para gestionar casos y seguridad de grupos | Mantener mientras el caso esté abierto; al cerrar, revisión manual y minimización. Definir plazo antes de automatizar | No hay purga automática general |
| Perfiles y actividad de usuarios/grupos | IDs, estado, preferencias, actividad y sanciones para prestar funciones del bot | Mientras la cuenta/grupo use la función correspondiente; revisar registros inactivos y permitir eliminación/minimización manual | No hay vencimiento uniforme |
| Compras, saldos, créditos y canjes | IDs, importes, movimientos y estados para entregar compras, resolver disputas y prevenir fraude | No borrar automáticamente hasta definir las obligaciones contables, contractuales y antifraude aplicables; conservar solo los campos necesarios | No hay purga automática general |
| Copias de seguridad | Copias de bases exportadas para recuperación ante fallos | Las copias contienen las mismas categorías de datos; restringir acceso y eliminarlas cuando caduquen según el plazo que se apruebe para cada categoría | No se ha verificado expiración automática fuera del bot |

## Medidas vigentes

- El historial de descargas se purga a los 30 días y los temporales locales a la hora.
- La limpieza manual de historiales requiere vista previa, confirmación y respaldo previo; está reservada al fundador.
- No se ejecutará borrado masivo ni se alterará la base de producción como parte de esta política.
- Los respaldos enviados a un chat privado de Telegram son copias adicionales; su borrado puede requerir acción en Telegram y no se controla desde la base.

## Pendientes antes de automatizar más borrados

1. Validar con el responsable qué campos son imprescindibles para solicitudes, moderación y compras.
2. Definir y aprobar plazos concretos por categoría, incluyendo respaldos y registros de auditoría.
3. Implementar purga con vista previa/log de conteos, exclusión de casos abiertos y opción de anonimización cuando corresponda.
4. Probar en una copia anonimizada y confirmar restauración antes de activar cualquier job sobre Turso.

La ley chilena 21.719 establece que los datos personales solo pueden conservarse durante el tiempo necesario para cumplir sus fines, con las excepciones legales aplicables. Su entrada en vigencia está fijada para el 1 de diciembre de 2026. Consulta el texto oficial de [Ley 21.719 en Ley Chile](https://www.leychile.cl/leychile/Navegar?idNorma=1209272&idParte=1).
