# Operación en Oracle Cloud

Este es el procedimiento para la instalación actual: una VM con Docker Compose, dos contenedores (`bot` y `web`) y Turso como base remota compartida. La configuración Compose está en [compose.yaml](compose.yaml).

## Servicios y acceso

- `bot` inicia el bot con long polling; debe ejecutarse en una sola instancia.
- `web` expone el panel y la API dentro de Compose en el puerto `8080`. En el host, Compose lo publica solo en `127.0.0.1:8080`.
- Turso conserva los datos fuera de los contenedores. Ambos servicios necesitan la misma URL y token.
- Cloudflare Quick Tunnel proporciona el acceso público actual al panel. Su URL temporal puede cambiar si el túnel se reinicia. No uses una dirección `trycloudflare.com` como dirección permanente.

## Secretos y configuración

Mantén `.env` en la VM, con permisos restringidos y fuera de Git. Nunca pegues sus valores en logs, capturas o chats.

Configura en `.env` las variables de [`.env.example`](.env.example) necesarias para el bot y la web, incluidas `BOT_TOKEN`, `DATABASE_BACKEND=turso`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `NEXORA_INTERNAL_API_KEY`, `NEXORA_PANEL_USER`, `NEXORA_PANEL_PASSWORD` y `NEXORA_PANEL_SECRET`. La URL del panel para los enlaces de Telegram se configura con `NEXORA_PANEL_URL` en el entorno del bot.

Usa una sola clave interna compartida por bot y web, una contraseña de panel fuerte y una clave de sesión estable. No vuelvas a inicializar ni importar datos sobre la base productiva.

## Iniciar o actualizar

Desde la carpeta del proyecto en la VM:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

`docker compose config --quiet` valida la sintaxis y la interpolación; no imprime los valores de configuración. Al actualizar, conserva el `.env` y el volumen `./app/data`. No ejecutes `down -v` ni borres la carpeta de datos.

Para revisar fallos recientes, consulta `docker compose logs --tail=100 bot web`; antes de compartir salida, quita cualquier secreto. `/health` debe responder y `/status` en Telegram debe mostrar `Web: 200`, `Worker: En línea` y `Turso (remoto)`.

## Acceso estable sin pagar por un dominio

Quick Tunnel sirve para probar, pero usa una URL aleatoria que puede cambiar. Para conservar la misma dirección sin pagar un dominio, se puede conectar un dominio que ya tengas a un Cloudflare Named Tunnel gratuito. Si no tienes un dominio propio, el enlace Quick Tunnel seguirá siendo temporal. El bot y el panel pueden continuar funcionando; cuando cambie el enlace público, actualiza `NEXORA_PANEL_URL` para que `/status` y `/paneladmin` muestren el acceso correcto.

Antes de reiniciar el túnel, comprueba que la web responda en `http://127.0.0.1:8080/health`. El túnel solo publica la web; no expongas el puerto del bot ni el puerto `8080` directamente a Internet.

## Recuperación

- Si la VM reinicia, `restart: unless-stopped` vuelve a iniciar los contenedores de Docker.
- Si la web no responde, consulta primero `docker compose ps` y los logs de `web`; después revisa que el contenedor `bot` pueda alcanzar `http://web:8080` dentro de Compose.
- Si el panel no abre desde fuera, revisa el proceso del túnel y su URL pública. Si la URL cambió, actualiza la variable del bot y reinícialo con `docker compose up -d bot`.
- Los datos productivos residen en Turso. Conserva el acceso a Turso y sigue el plan de respaldos; no confíes en el disco efímero del contenedor como copia única.
- Revisa el uso de Oracle Cloud y los límites de Always Free en la consola. Un recurso marcado como elegible no garantiza capacidad disponible ni que todos los recursos asociados estén cubiertos.
