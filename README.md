# NEXORA ONE

Bot: **@NexoraOneRoBot**. Dueño: **@PeruDoxer (7454664711)**.
Cuenta oficial: **@OficialNexora (7151644287)**, sin privilegios automáticos.
Todo permanece dentro de `DoxerTubeBot`. Ver `DEPLOY-NORTHFLANK.md` para montar bot y web.

Bot único para Telegram. Reúne moderación, descargas, juegos y servicios. Créditos y soles usan almacenamiento separado; la web se ejecuta como un servicio independiente.

## Funciones principales

- Moderación: anti-link, antiflood, palabras bloqueadas, captcha, warns, mute, ban, reportes, tickets y logs.
- Administración desde `/menu`: reglas, bienvenida, staff, rangos, notas, comandos personalizados y estadísticas.
- Multimedia: TikTok, Instagram Reels, YouTube y Facebook; video, audio MP3 o documento.
- Economía: registro, perfil/cartera, recompensa diaria, minería, pesca, casino y rankings.
- Comunidad: sorteos, encuestas, niveles, roles, mensajes programados y aprobación manual.
- Utilidad: calculadora segura, letras de canciones, favoritos, historial y cola de descargas.

Los enlaces de TikTok, Reels y Shorts enviados sin comando se descargan automáticamente.

## Configuración local

1. Instala Python 3.11 o superior y FFmpeg.
2. Copia `.env.example` como `.env` y agrega el token creado con BotFather.
3. Ejecuta:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

En Telegram agrega el bot al grupo como administrador. Para que pueda revisar todos los mensajes, desactiva el modo privacidad en BotFather con `/setprivacy`.

## Comandos añadidos

- `/play canción o enlace`: descarga audio.
- `/playvideo`, `/ytmp4`: descarga video.
- `/playdoc`: descarga video como documento.
- `/tiktok`, `/instagram`, `/facebook`: descarga el enlace indicado.
- `/register`, `/perfil`, `/daily`, `/minar`, `/pescar`, `/tragamonedas`, `/ruleta`.
- `/ranksoles`, `/ranknivel`, `/rankrep`.
- `/calcular 2*(5+3)`.
- `/favoritos`, `/historial`, `/cola`.
- `/programar`, `/programardiario`, `/programarsemanal`.
- `/sorteo`, `/encuesta`, `/nivel`, `/rankactividad`.
- `/exportarconfig`, `/importarconfig`, `/copiarconfig`.
- `/autolimpieza 15`, `/idioma es|en`, `/canalobligatorio @canal`.

Todos los comandos y la administración están organizados dentro del menú único `/menu`.

## Variables para reglas y bienvenida

Los textos configurables aceptan estas variables:

- `{group}`: nombre del grupo.
- `{name}`: nombre de la persona.
- `{username}`: usuario de Telegram.
- `{members}`: cantidad de miembros.
- `{id}`: ID de la persona.

Ejemplo:

```text
/setrules #{group} → REGLAS DEL GRUPO
Respeta al staff y evita el spam.
```

## Permisos recomendados en Telegram

Agrega el bot como administrador con permisos para eliminar mensajes, restringir y expulsar usuarios, fijar mensajes, invitar usuarios y administrar administradores si utilizarás promociones. En el canal de logs, copias o membresía obligatoria debe poder publicar y consultar miembros. Desactiva el modo privacidad desde BotFather para que la moderación pueda leer los mensajes del grupo.

## Datos persistentes

SQLite guarda reglas, economía, notas, favoritos, sorteos y programaciones en `DB_PATH`. En producción monta almacenamiento persistente en `/bot/app/data`; sin volumen, un reemplazo del contenedor puede borrar los cambios posteriores al último backup.

## Hosting gratuito sin suspensión

La opción recomendada para este proyecto es Northflank Sandbox: ejecuta servicios Docker continuamente sin suspensión. Consulta `DEPLOY-NORTHFLANK.md`.

No publiques `.env` ni `app/data/bot.db`.
