import asyncio
import html
import hashlib
import json
import logging
import os
import re
import secrets
import signal
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict, deque
from pathlib import Path
from time import monotonic, time
from urllib.parse import quote_plus, urlencode, urlparse
from urllib.request import Request, urlopen

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.media_group import MediaGroupBuilder
from nexora import async_db as aiosqlite
from yt_dlp import YoutubeDL

from app.config import DB_PATH, OWNER_USER_ID

router = Router()
logger = logging.getLogger(__name__)
SUPPORTED = ("youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch")
MAX_UPLOAD = 49 * 1024 * 1024
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "media_cache"
CACHE_MAX_BYTES = 250 * 1024 * 1024
SEARCH_CACHE: dict[str, dict] = {}
MEDIA_REQUESTS: dict[str, dict] = {}
DOWNLOAD_PROGRESS: dict[str, dict] = {}
DOWNLOAD_OWNERS: dict[str, int] = {}
DOWNLOAD_PROCESSES: dict[str, asyncio.subprocess.Process] = {}
DOWNLOAD_STAGES: dict[str, asyncio.Task] = {}
ACTIVE_DOWNLOADS: dict[int, str] = {}
DOWNLOAD_QUEUE: list[str] = []
CANCELLED_DOWNLOADS: set[str] = set()
DOWNLOAD_LIMITS: dict[int, deque] = defaultdict(deque)
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)
TIKTOK_API = "https://www.tikwm.com/api/"
MAX_CAROUSEL_IMAGES = 35
MAX_INSTAGRAM_ITEMS = 20
MAX_DOWNLOAD_SECONDS = 15 * 60
REQUEST_TTL_SECONDS = 30 * 60


class DownloadCancelled(Exception):
    pass


def _terminate_process(process: asyncio.subprocess.Process):
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.terminate()
        except ProcessLookupError:
            pass


def cancel_user_download(user_id: int) -> bool:
    job_id = ACTIVE_DOWNLOADS.get(user_id)
    if not job_id:
        return False
    CANCELLED_DOWNLOADS.add(job_id)
    stage = DOWNLOAD_STAGES.get(job_id)
    if stage:
        stage.cancel()
    process = DOWNLOAD_PROCESSES.get(job_id)
    if process:
        _terminate_process(process)
    return True


async def _stage(job_id, operation):
    # Aiogram methods are awaitable objects, not coroutine objects.
    task = asyncio.ensure_future(operation)
    DOWNLOAD_STAGES[job_id] = task
    try:
        return await task
    except asyncio.CancelledError:
        if job_id in CANCELLED_DOWNLOADS:
            raise DownloadCancelled()
        raise
    finally:
        DOWNLOAD_STAGES.pop(job_id, None)


def clear_user_media_requests(user_id: int) -> bool:
    removed = False
    for storage in (SEARCH_CACHE, MEDIA_REQUESTS):
        for token, request in list(storage.items()):
            if request.get("user_id") == user_id:
                storage.pop(token, None)
                removed = True
    return removed


def _remember_request(storage: dict, token: str, request: dict):
    storage[token] = {**request, "_created_at": monotonic()}


def _expire_memory_requests():
    cutoff = monotonic() - REQUEST_TTL_SECONDS
    for storage in (SEARCH_CACHE, MEDIA_REQUESTS):
        for token, request in list(storage.items()):
            if request.get("_created_at", cutoff) <= cutoff:
                storage.pop(token, None)


def _friendly_download_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "tiempo máximo" in text or isinstance(exc, asyncio.TimeoutError):
        return "La descarga excedió el tiempo máximo y fue detenida automáticamente."
    if "file is too big" in text or "request entity too large" in text:
        return "El archivo supera el límite de Telegram. Prueba menor calidad o un video más corto."
    if "unsupported url" in text:
        return "El enlace no es compatible o está incompleto."
    if "private" in text or "login" in text or "sign in" in text:
        return "El contenido es privado o requiere iniciar sesión."
    if "copyright" in text or "not available" in text or "unavailable" in text:
        return "El contenido no está disponible o tiene restricciones."
    if "timed out" in text or "timeout" in text:
        return "La plataforma tardó demasiado. Intenta nuevamente en unos minutos."
    return "La plataforma rechazó la descarga o el enlace dejó de estar disponible."


def _cleanup_stale_downloads(max_age_seconds: int = 3600):
    now = time()
    temp_dir = Path(tempfile.gettempdir())
    for path in temp_dir.glob("doxertube_*"):
        try:
            if path.is_dir() and now - path.stat().st_mtime > max_age_seconds:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


async def media_cleanup_loop():
    while True:
        try:
            await _init_media_storage()
            await asyncio.to_thread(_cleanup_stale_downloads)
            _expire_memory_requests()
            await _trim_cache()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM download_history WHERE created_at < DATETIME('now','-30 days')")
                await db.commit()
        except Exception:
            pass
        await asyncio.sleep(60 * 60)


async def _init_media_storage():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS media_cache (
            cache_key TEXT PRIMARY KEY, file_path TEXT NOT NULL, title TEXT,
            uploader TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS download_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL, query TEXT NOT NULL, media_type TEXT NOT NULL,
            quality TEXT, title TEXT, status TEXT NOT NULL, cache_hit INTEGER DEFAULT 0,
            document INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        try:
            await db.execute("ALTER TABLE download_history ADD COLUMN document INTEGER DEFAULT 0")
        except Exception:
            pass
        await db.commit()


def _cache_key(query: str, audio: bool, quality: str) -> str:
    value = f"{query.strip()}|{audio}|{quality}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


async def _get_cached(query: str, audio: bool, quality: str):
    key = _cache_key(query, audio, quality)
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT file_path,title,uploader FROM media_cache WHERE cache_key=?", (key,)
        )).fetchone()
        if not row:
            return None
        path = Path(row[0])
        if not path.exists():
            await db.execute("DELETE FROM media_cache WHERE cache_key=?", (key,))
            await db.commit()
            return None
        await db.execute("UPDATE media_cache SET last_used=CURRENT_TIMESTAMP WHERE cache_key=?", (key,))
        await db.commit()
        return path, {"title": row[1], "uploader": row[2]}


async def _save_cached(query: str, audio: bool, quality: str, source: Path, info: dict):
    key = _cache_key(query, audio, quality)
    destination = CACHE_DIR / f"{key}{source.suffix.lower()}"
    await asyncio.to_thread(shutil.copy2, source, destination)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT OR REPLACE INTO media_cache
            (cache_key,file_path,title,uploader,created_at,last_used)
            VALUES(?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
            (key, str(destination), info.get("title"), info.get("uploader")))
        await db.commit()
    await _trim_cache()
    return destination


async def _trim_cache():
    files = [path for path in CACHE_DIR.glob("*") if path.is_file()]
    total = sum(path.stat().st_size for path in files)
    if total <= CACHE_MAX_BYTES:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute("SELECT cache_key,file_path FROM media_cache ORDER BY last_used ASC")).fetchall()
        for key, file_path in rows:
            if total <= CACHE_MAX_BYTES:
                break
            path = Path(file_path)
            if path.exists():
                size = path.stat().st_size
                path.unlink(missing_ok=True)
                total -= size
            await db.execute("DELETE FROM media_cache WHERE cache_key=?", (key,))
        await db.commit()


async def _add_history(user_id: int, chat_id: int, query: str, audio: bool, quality: str,
                       title: str | None, status: str, cache_hit: bool = False, document: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""INSERT INTO download_history
            (user_id,chat_id,query,media_type,quality,title,status,cache_hit,document)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (user_id, chat_id, query[:500], "audio" if audio else "video", quality,
             title, status, 1 if cache_hit else 0, 1 if document else 0))
        await db.commit()
        return cursor.lastrowid


def _history_actions(history_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ Guardar favorito", callback_data=f"media:favorite:{history_id}")
    builder.button(text="🔁 Descargar otra vez", callback_data=f"media:repeat:{history_id}")
    builder.adjust(2)
    return builder.as_markup()


def _quality_keyboard(token: str, audio: bool):
    builder = InlineKeyboardBuilder()
    if audio:
        builder.button(text="🎵 MP3 128 kbps", callback_data=f"media:audioq:{token}:128")
        builder.button(text="🎧 MP3 192 kbps", callback_data=f"media:audioq:{token}:192")
    else:
        builder.button(text="📱 Video 360p", callback_data=f"media:videoq:{token}:360")
        builder.button(text="📺 Video 720p", callback_data=f"media:videoq:{token}:720")
    builder.adjust(1)
    return builder.as_markup()


def _direct_keyboard(token: str, carousel: bool = False):
    builder = InlineKeyboardBuilder()
    label = "🖼 Descargar fotos" if carousel else "📥 Descargar video"
    action = "carousel" if carousel else "direct"
    builder.button(text=label, callback_data=f"media:{action}:{token}")
    builder.button(text="❌ Cancelar", callback_data=f"media:dismiss:{token}")
    builder.adjust(1)
    return builder.as_markup()


def _instagram_keyboard(token: str, count: int):
    builder = InlineKeyboardBuilder()
    label = f"📥 Descargar publicación ({count})" if count > 1 else "📥 Descargar publicación"
    builder.button(text=label, callback_data=f"media:instagram:{token}")
    builder.button(text="❌ Cancelar", callback_data=f"media:dismiss:{token}")
    builder.adjust(1)
    return builder.as_markup()


def _retry_keyboard(request: dict):
    token = secrets.token_hex(4)
    _remember_request(MEDIA_REQUESTS, token, request)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔁 Reintentar", callback_data=f"media:retry:{token}")
    builder.button(text="❌ Cerrar", callback_data=f"media:dismiss:{token}")
    builder.adjust(2)
    return builder.as_markup()


def _is_tiktok_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return False
    return host == "tiktok.com" or host.endswith(".tiktok.com")


def _is_tiktok_asset_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return False
    trusted_suffixes = (".tiktokcdn.com", ".tiktokcdn-us.com", ".byteoversea.com",
                        ".ibytedtos.com", ".muscdn.com")
    return parsed.scheme == "https" and any(host.endswith(suffix) for suffix in trusted_suffixes)


def _is_instagram_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return False
    return host == "instagram.com" or host.endswith(".instagram.com")


def _is_instagram_asset_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return False
    return parsed.scheme == "https" and (
        host.endswith(".cdninstagram.com") or host.endswith(".fbcdn.net")
    )


def _extract_instagram_urls(url: str) -> list[str]:
    if not _is_instagram_url(url):
        raise ValueError("El enlace no pertenece a Instagram.")
    result = subprocess.run(
        [sys.executable, "-m", "gallery_dl", "-q", "-g", "--range", f"1-{MAX_INSTAGRAM_ITEMS}", url],
        capture_output=True, text=True, timeout=35, check=False,
    )
    urls = []
    for line in result.stdout.splitlines():
        candidate = line.strip()
        if _is_instagram_asset_url(candidate) and candidate not in urls:
            urls.append(candidate)
    if not urls:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "sin archivos públicos"
        raise RuntimeError(detail)
    return urls


def _download_instagram_item(url: str, destination: Path) -> tuple[Path, str]:
    if not _is_instagram_asset_url(url):
        raise ValueError("Instagram devolvió una ubicación no permitida.")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.instagram.com/"})
    with urlopen(request, timeout=35) as response:
        content_type = response.headers.get_content_type()
        if content_type.startswith("image/"):
            suffix, kind = ".jpg", "photo"
        elif content_type.startswith("video/"):
            suffix, kind = ".mp4", "video"
        else:
            raise RuntimeError("Instagram devolvió un archivo no válido.")
        final_path = destination.with_suffix(suffix)
        total = 0
        with final_path.open("wb") as output:
            while chunk := response.read(256 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD:
                    raise RuntimeError("Un archivo supera el límite de Telegram.")
                output.write(chunk)
    return final_path, kind


def _fetch_tiktok_data(url: str) -> dict:
    if not _is_tiktok_url(url):
        raise ValueError("El enlace no pertenece a TikTok.")
    endpoint = f"{TIKTOK_API}?{urlencode({'url': url, 'hd': '1'})}"
    request = Request(endpoint, headers={"User-Agent": "NEXORA ONE/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data") if payload.get("code") == 0 else None
    if not isinstance(data, dict):
        raise RuntimeError(payload.get("msg") or "TikTok no devolvió información.")
    images = [item for item in data.get("images") or [] if isinstance(item, str) and _is_tiktok_asset_url(item)]
    if images:
        return {"kind": "carousel", "images": images[:MAX_CAROUSEL_IMAGES],
                "title": data.get("title") or "Carrusel de TikTok"}
    video_url = data.get("hdplay") or data.get("play")
    if isinstance(video_url, str) and _is_tiktok_asset_url(video_url) and int(data.get("duration") or 0) > 0:
        return {"kind": "video", "video_url": video_url,
                "title": data.get("title") or "Video de TikTok"}
    raise RuntimeError("La publicación no contiene fotos ni video descargable.")


def _download_remote_file(url: str, destination: Path):
    if not _is_tiktok_asset_url(url):
        raise ValueError("TikTok devolvió una ubicación no permitida.")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.tiktok.com/"})
    with urlopen(request, timeout=30) as response, destination.open("wb") as output:
        content_type = response.headers.get_content_type()
        if not content_type.startswith("image/"):
            raise RuntimeError("TikTok devolvió un archivo no válido.")
        total = 0
        while chunk := response.read(256 * 1024):
            total += len(chunk)
            if total > 15 * 1024 * 1024:
                raise RuntimeError("Una imagen supera el límite permitido.")
            output.write(chunk)


def _rate_limit(user_id: int, limit: int = 3, window_seconds: int = 600) -> int:
    now = monotonic()
    requests = DOWNLOAD_LIMITS[user_id]
    while requests and now - requests[0] > window_seconds:
        requests.popleft()
    if len(requests) >= limit:
        return max(1, int(window_seconds - (now - requests[0])))
    requests.append(now)
    return 0


async def _has_free_downloads(user_id: int) -> bool:
    if user_id == OWNER_USER_ID:
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT 1 FROM download_exemptions WHERE user_id=?", (user_id,)
        )).fetchone()
    return row is not None


async def _download_policy() -> tuple[int, int, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS download_policy (
            id INTEGER PRIMARY KEY CHECK(id=1), max_downloads INTEGER NOT NULL DEFAULT 3,
            window_seconds INTEGER NOT NULL DEFAULT 600, parallel_downloads INTEGER NOT NULL DEFAULT 3)""")
        await db.execute("INSERT OR IGNORE INTO download_policy VALUES(1,3,600,3)")
        await db.commit()
        row = await (await db.execute(
            "SELECT max_downloads,window_seconds,parallel_downloads FROM download_policy WHERE id=1"
        )).fetchone()
    return int(row[0]), int(row[1]), int(row[2])


def _search_youtube_html(query: str) -> list[dict]:
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept-Language": "es-419,es;q=0.9,en;q=0.7",
    })
    with urlopen(request, timeout=12) as response:
        page = response.read().decode("utf-8", errors="ignore")
    results, seen = [], set()
    for match in re.finditer(r'"videoRenderer":\{"videoId":"([^"]+)"', page):
        video_id = match.group(1)
        if video_id in seen:
            continue
        block = page[match.start():match.start() + 9000]
        title_match = re.search(r'"title":\{"runs":\[\{"text":"((?:\\.|[^"])*)"', block)
        if not title_match:
            continue
        try:
            title = json.loads(f'"{title_match.group(1)}"')
        except json.JSONDecodeError:
            title = title_match.group(1)
        owner_match = re.search(r'"ownerText":\{"runs":\[\{"text":"((?:\\.|[^"])*)"', block)
        duration_match = re.search(r'"lengthText":.*?"simpleText":"([^"]+)"', block)
        channel = ""
        if owner_match:
            try:
                channel = json.loads(f'"{owner_match.group(1)}"')
            except json.JSONDecodeError:
                channel = owner_match.group(1)
        results.append({"id": video_id, "title": html.unescape(title),
                        "channel": html.unescape(channel),
                        "duration_text": duration_match.group(1) if duration_match else "?:??"})
        seen.add(video_id)
        if len(results) == 40:
            break
    return results


def _format_duration(value) -> str:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return "?:??"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def _format_bytes(value) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return "?"


def _search_youtube(query: str) -> list[dict]:
    """Obtiene hasta 40 resultados y conserva el buscador web como respaldo."""
    results, seen = [], set()
    try:
        options = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "playlistend": 40,
            "socket_timeout": 18,
        }
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearch40:{query}", download=False)
        for item in (info or {}).get("entries") or []:
            video_id = item.get("id")
            if not video_id or video_id in seen:
                continue
            results.append({
                "id": video_id,
                "title": item.get("title") or "Sin titulo",
                "channel": item.get("channel") or item.get("uploader") or "",
                "duration_text": _format_duration(item.get("duration")),
            })
            seen.add(video_id)
            if len(results) >= 40:
                return results
    except Exception:
        pass

    try:
        fallback = _search_youtube_html(query)
    except Exception:
        fallback = []
    for item in fallback:
        if item["id"] not in seen:
            results.append(item)
            seen.add(item["id"])
        if len(results) >= 40:
            break
    return results


def _search_menu(results: list[dict], token: str, page: int, mode: str = "audio"):
    page_size = 5
    total_pages = max(1, (len(results) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    visible = results[start:start + page_size]
    keyboard = InlineKeyboardBuilder()
    heading = "🎵 Elige una canción" if mode == "audio" else "🎬 Elige un video"
    lines = [f"<b>{heading}</b> — página {page + 1}/{total_pages}", ""]
    for position, item in enumerate(visible, start + 1):
        title = (item.get("title") or "Sin título")[:70]
        channel = (item.get("channel") or "")[:35]
        duration = item.get("duration_text") or "?:??"
        lines.append(f"{position}. {html.escape(title)} — {html.escape(channel)} [{duration}]")
        keyboard.button(
            text=f"{position}. {title[:35]}",
            callback_data=f"media:select:{token}:{item['id']}",
        )
    keyboard.adjust(1)
    navigation = []
    if page > 0:
        navigation.append(("⬅️ Anterior", f"media:page:{token}:{page - 1}"))
    if page + 1 < total_pages:
        navigation.append(("Siguiente ➡️", f"media:page:{token}:{page + 1}"))
    for label, callback_data in navigation:
        keyboard.button(text=label, callback_data=callback_data)
    if navigation:
        keyboard.adjust(*([1] * len(visible)), len(navigation))
    return "\n".join(lines), keyboard.as_markup()


def _duration(seconds) -> str:
    try:
        seconds = int(seconds or 0)
        return f"{seconds // 60}:{seconds % 60:02d}"
    except (TypeError, ValueError):
        return "?:??"


async def _download_process(query: str, audio: bool = False, quality: str = "720", job_id: str = "") -> tuple[Path, Path, dict]:
    work = Path(tempfile.mkdtemp(prefix="doxertube_"))
    # Generic CDN IDs can contain the entire signed URL. Bound both fields.
    target = str(work / "%(title).120B-%(id).64B.%(ext)s")
    if audio:
        format_value = "bestaudio/best"
    elif quality == "best":
        format_value = "best[filesize<49M]/best"
    else:
        format_value = f"best[height<={quality}][filesize<49M]/best[height<={quality}]/best[filesize<49M]/best"
    source = query if query.lower().startswith(("http://", "https://")) else f"ytsearch1:{query}"
    command = [
        sys.executable, "-m", "yt_dlp", source, "--no-playlist", "--newline",
        "--no-warnings", "-o", target, "-f", format_value,
        "--progress-template",
        "download:download:%(progress._percent_str)s|%(progress.eta)s|%(progress.downloaded_bytes)s|%(progress.total_bytes,progress.total_bytes_estimate)s|%(progress.speed)s",
        "--retries", "3", "--fragment-retries", "3", "--socket-timeout", "20",
    ]
    if audio:
        command.extend(["-x", "--audio-format", "mp3", "--audio-quality", f"{quality}K"])
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    DOWNLOAD_PROCESSES[job_id] = process
    output = []
    try:
        while True:
            if job_id in CANCELLED_DOWNLOADS and process.returncode is None:
                _terminate_process(process)
            line_bytes = await asyncio.wait_for(process.stdout.readline(), timeout=60)
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="ignore").strip()
            output.append(line)
            progress = re.search(r"download:\s*([\d.]+)%\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)", line)
            if progress:
                DOWNLOAD_PROGRESS[job_id] = {
                    "percent": int(float(progress.group(1))),
                    "eta": progress.group(2) if progress.group(2) not in {"NA", "None"} else None,
                    "downloaded": progress.group(3),
                    "total": progress.group(4),
                    "speed": progress.group(5),
                }
            elif "ExtractAudio" in line or "Merging formats" in line:
                DOWNLOAD_PROGRESS[job_id] = {"percent": 100, "processing": True}
        return_code = await process.wait()
    except BaseException:
        if process.returncode is None:
            _terminate_process(process)
            await process.wait()
        shutil.rmtree(work, ignore_errors=True)
        raise
    finally:
        DOWNLOAD_PROCESSES.pop(job_id, None)
    if job_id in CANCELLED_DOWNLOADS:
        shutil.rmtree(work, ignore_errors=True)
        raise DownloadCancelled()
    if return_code != 0:
        detail = next((line for line in reversed(output) if line), "yt-dlp terminó con error")
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError(detail)
    files = [p for p in work.iterdir() if p.is_file()]
    if not files:
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError("La descarga no produjo ningún archivo.")
    path = max(files, key=lambda p: p.stat().st_size)
    return path, work, {"title": path.stem, "uploader": None}


async def _send_download(message: Message, query: str, audio: bool = False, document: bool = False,
                         quality: str = "720", requester_id: int | None = None,
                         status_message: Message | None = None, title_override: str | None = None,
                         source_url: str | None = None):
    download_query = query
    query = source_url or query
    user_id = requester_id or message.from_user.id
    await _init_media_storage()
    if user_id in ACTIVE_DOWNLOADS:
        await message.reply("⏳ Ya tienes una descarga activa. Cancélala o espera que termine.")
        return
    if len(DOWNLOAD_QUEUE) >= 6:
        await message.reply("🧠 La cola está llena. Espera que termine alguna descarga.")
        return
    free_downloads = await _has_free_downloads(user_id)
    max_downloads, window_seconds, _ = await _download_policy()
    retry = 0 if free_downloads else _rate_limit(user_id, max_downloads, window_seconds)
    if retry:
        minutes = max(1, window_seconds // 60)
        await message.reply(
            f"🚦 Límite: {max_downloads} descargas cada {minutes} minutos. "
            f"Intenta en {retry} segundos."
        )
        return
    job_id = secrets.token_hex(4)
    # Las consultas anteriores ceden el control: comprobar de nuevo antes de reservar.
    if user_id in ACTIVE_DOWNLOADS:
        await message.reply("⏳ Ya tienes una descarga activa. Usa /cancelar para detenerla.")
        return
    ACTIVE_DOWNLOADS[user_id] = job_id
    DOWNLOAD_OWNERS[job_id] = user_id
    DOWNLOAD_QUEUE.append(job_id)
    cancel = InlineKeyboardBuilder()
    cancel.button(text="❌ Cancelar descarga", callback_data=f"media:cancel:{job_id}")
    position = DOWNLOAD_QUEUE.index(job_id) + 1
    initial = "⏳ Preparando descarga…" if position == 1 else f"🕓 En cola · posición {position}"
    try:
        if status_message:
            status = status_message
            await status.edit_text(initial, reply_markup=cancel.as_markup())
        else:
            status = await message.reply(initial, reply_markup=cancel.as_markup())
    except Exception:
        ACTIVE_DOWNLOADS.pop(user_id, None)
        DOWNLOAD_OWNERS.pop(job_id, None)
        if job_id in DOWNLOAD_QUEUE:
            DOWNLOAD_QUEUE.remove(job_id)
        raise
    work = None
    cache_hit = False
    semaphore_acquired = False
    try:
        await _stage(job_id, DOWNLOAD_SEMAPHORE.acquire())
        semaphore_acquired = True
        if job_id in CANCELLED_DOWNLOADS:
            raise DownloadCancelled()
        if job_id in DOWNLOAD_QUEUE:
            DOWNLOAD_QUEUE.remove(job_id)
        await status.edit_text("⏳ Iniciando tu descarga…", reply_markup=cancel.as_markup())
        media_type = "audio" if audio else "document" if document else "video"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS telegram_media (cache_key TEXT PRIMARY KEY, file_id TEXT NOT NULL, title TEXT)")
            tg_key = _cache_key(query, audio, quality) + media_type
            tg_cached = await (await db.execute("SELECT file_id,title FROM telegram_media WHERE cache_key=?", (tg_key,))).fetchone()
        if tg_cached:
            await status.edit_text("⚡ Enviando archivo guardado en Telegram…", reply_markup=cancel.as_markup())
            title = (title_override or tg_cached[1] or "Archivo")[:1000]
            try:
                if audio:
                    operation = message.answer_audio(tg_cached[0], title=title[:200])
                elif document:
                    operation = message.answer_document(tg_cached[0], caption=f"📥 {title}")
                else:
                    operation = message.answer_video(tg_cached[0], caption=f"🎬 {title}")
                sent = await _stage(job_id, operation)
            except DownloadCancelled:
                raise
            except Exception:
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("DELETE FROM telegram_media WHERE cache_key=?", (tg_key,))
                    await db.commit()
            else:
                history_id = await _add_history(user_id, message.chat.id, query, audio, quality, title, "success", True, document)
                try:
                    await status.delete()
                    await sent.edit_reply_markup(reply_markup=_history_actions(history_id))
                except Exception:
                    logger.warning("Archivo enviado; no se pudo actualizar su interfaz")
                return
        await asyncio.to_thread(_cleanup_stale_downloads)
        cached = await _get_cached(query, audio, quality)
        if cached:
            path, info = cached
            if title_override is not None:
                info["title"] = title_override
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("UPDATE media_cache SET title=? WHERE cache_key=?",
                                     (title_override, _cache_key(query, audio, quality)))
                    await db.commit()
            cache_hit = True
            await status.edit_text("⚡ Archivo encontrado en caché. Enviando…")
        else:
            if _is_tiktok_url(query) and not source_url:
                data = await _stage(job_id, asyncio.wait_for(asyncio.to_thread(_fetch_tiktok_data, query), timeout=25))
                if data.get("kind") != "video":
                    raise RuntimeError("Esta publicación es un carrusel; vuelve a enviar el enlace para descargar sus fotos.")
                download_query = data["video_url"]
                title_override = data.get("title") or "Video de TikTok"
            task = asyncio.create_task(_stage(job_id, _download_process(download_query, audio, quality, job_id)))
            last_percent = -1
            started_at = monotonic()
            while not task.done():
                # Despertar inmediatamente al completar la descarga.
                await asyncio.wait({task}, timeout=2)
                if task.done():
                    break
                if monotonic() - started_at > MAX_DOWNLOAD_SECONDS:
                    process = DOWNLOAD_PROCESSES.get(job_id)
                    if process:
                        _terminate_process(process)
                    try:
                        await asyncio.wait_for(task, timeout=10)
                    except Exception:
                        pass
                    raise asyncio.TimeoutError("La descarga excedió el tiempo máximo")
                progress = DOWNLOAD_PROGRESS.get(job_id, {})
                percent = progress.get("percent", 0)
                progress_state = (percent, progress.get("processing"), progress.get("downloaded"))
                if progress_state != last_percent:
                    last_percent = progress_state
                    if progress.get("processing"):
                        text = "⚙️ Descarga completa. Procesando archivo…"
                    else:
                        eta = progress.get("eta")
                        eta_text = f" · faltan ~{eta}s" if eta is not None else ""
                        downloaded = _format_bytes(progress.get("downloaded"))
                        total = _format_bytes(progress.get("total"))
                        speed = _format_bytes(progress.get("speed"))
                        details = ""
                        if downloaded != "?":
                            details = f"\n💾 {downloaded}" + (f" / {total}" if total != "?" else " descargados")
                        if speed != "?":
                            details += f" · ⚡ {speed}/s"
                        text = (f"📥 Descargando: {percent}%{eta_text}{details}" if progress
                                else "📥 Conectando con el servidor…")
                    try:
                        await status.edit_text(text, reply_markup=cancel.as_markup())
                    except Exception:
                        pass
            path, work, info = await task
            if title_override is not None:
                info["title"] = title_override
            if path.stat().st_size <= MAX_UPLOAD:
                path = await _save_cached(query, audio, quality, path, info)
        if job_id in CANCELLED_DOWNLOADS:
            raise DownloadCancelled()
        if path.stat().st_size > MAX_UPLOAD:
            await status.edit_text("❌ El archivo supera 49 MB. Prueba con otro video o una versión más corta.")
            return
        title = (info.get("title") or "Video")[:1000]
        media = FSInputFile(path, filename=path.name)
        await status.edit_text("📤 Enviando a Telegram…", reply_markup=cancel.as_markup())
        if audio:
            sent_media = await _stage(job_id, message.answer_audio(media, title=title[:200], performer=info.get("uploader")))
        elif document:
            sent_media = await _stage(job_id, message.answer_document(media, caption=f"📥 {title}"))
        else:
            sent_media = await _stage(job_id, message.answer_video(media, caption=f"🎬 {title}", supports_streaming=True))
        file_id = getattr(sent_media, media_type).file_id
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO telegram_media VALUES (?,?,?)", (tg_key, file_id, title))
            await db.commit()
        await status.delete()
        history_id = await _add_history(user_id, message.chat.id, query, audio, quality, title, "success", cache_hit, document)
        try:
            await sent_media.edit_reply_markup(reply_markup=_history_actions(history_id))
        except Exception:
            pass
    except DownloadCancelled:
        await _add_history(user_id, message.chat.id, query, audio, quality, None, "cancelled", document=document)
        await status.edit_text("✅ Descarga cancelada.")
    except Exception as exc:
        if job_id in CANCELLED_DOWNLOADS:
            await _add_history(user_id, message.chat.id, query, audio, quality, None, "cancelled", document=document)
            await status.edit_text("✅ Descarga cancelada.")
            return
        await _add_history(user_id, message.chat.id, query, audio, quality, None, "failed", document=document)
        logger.exception("Falló una descarga multimedia para el usuario %s", user_id)
        request = {"query": query, "user_id": user_id, "audio": audio,
                   "document": document, "quality": quality, "title_override": title_override}
        await status.edit_text(
            f"❌ No pude descargarlo. {_friendly_download_error(exc)}\n\n"
            "Puedes reintentar sin enviar otra vez el enlace.",
            reply_markup=_retry_keyboard(request),
        )
    finally:
        ACTIVE_DOWNLOADS.pop(user_id, None)
        DOWNLOAD_OWNERS.pop(job_id, None)
        DOWNLOAD_PROGRESS.pop(job_id, None)
        CANCELLED_DOWNLOADS.discard(job_id)
        if job_id in DOWNLOAD_QUEUE:
            DOWNLOAD_QUEUE.remove(job_id)
        if semaphore_acquired:
            DOWNLOAD_SEMAPHORE.release()
        if work:
            shutil.rmtree(work, ignore_errors=True)


@router.message(Command("cola"))
async def download_queue(message: Message):
    if not DOWNLOAD_QUEUE and not DOWNLOAD_PROCESSES:
        await message.reply("✅ No hay descargas esperando en este momento.")
        return
    lines = ["📥 <b>Cola de descargas</b>", ""]
    active_jobs = set(DOWNLOAD_PROCESSES)
    ordered = list(active_jobs) + [job for job in DOWNLOAD_QUEUE if job not in active_jobs]
    for index, job_id in enumerate(ordered, 1):
        owner = DOWNLOAD_OWNERS.get(job_id)
        progress = DOWNLOAD_PROGRESS.get(job_id, {}).get("percent", 0)
        state = f"descargando {progress}%" if job_id in active_jobs else f"espera #{index}"
        marker = " (tú)" if message.from_user and owner == message.from_user.id else ""
        lines.append(f"{index}. Usuario <code>{owner}</code> · {state}{marker}")
    keyboard = None
    if message.from_user and message.from_user.id in ACTIVE_DOWNLOADS:
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Cancelar mi descarga", callback_data=f"media:cancel:{ACTIVE_DOWNLOADS[message.from_user.id]}")
        keyboard = builder.as_markup()
    await message.reply("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("play"))
async def play(message: Message, command: CommandObject):
    if not command.args:
        await message.reply("Usa /play nombre o enlace de YouTube")
        return
    status = await message.reply("🔎 Buscando canciones…")
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(_search_youtube, command.args), timeout=45
        )
        if not results:
            await status.edit_text("❌ No encontré canciones con ese nombre.")
            return
        token = secrets.token_hex(4)
        if len(SEARCH_CACHE) >= 100:
            SEARCH_CACHE.pop(next(iter(SEARCH_CACHE)))
        _remember_request(SEARCH_CACHE, token, {"results": results, "user_id": message.from_user.id, "mode": "audio"})
        text, markup = _search_menu(results, token, 0, "audio")
        await status.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except asyncio.TimeoutError:
        await status.edit_text("YouTube tardó demasiado en responder. Intenta nuevamente.")
    except Exception as exc:
        await status.edit_text(f"❌ No pude buscar ahora. {str(exc).splitlines()[-1][:250]}")


@router.callback_query(F.data.startswith("media:page:"))
async def change_search_page(callback: CallbackQuery):
    _, _, token, page_text = callback.data.split(":", 3)
    cached = SEARCH_CACHE.get(token)
    if not cached:
        await callback.answer("Esta búsqueda ya venció. Usa /play nuevamente.", show_alert=True)
        return
    if callback.from_user.id != cached["user_id"]:
        await callback.answer("Este menú pertenece a otra persona.", show_alert=True)
        return
    text, markup = _search_menu(cached["results"], token, int(page_text), cached.get("mode", "audio"))
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("media:select:"))
async def choose_search_result(callback: CallbackQuery):
    _, _, search_token, video_id = callback.data.split(":", 3)
    cached = SEARCH_CACHE.get(search_token)
    if not cached or cached["user_id"] != callback.from_user.id:
        await callback.answer("Esta búsqueda venció o pertenece a otra persona.", show_alert=True)
        return
    mode = cached.get("mode", "audio")
    token = secrets.token_hex(4)
    _remember_request(MEDIA_REQUESTS, token, {
        "query": f"https://www.youtube.com/watch?v={video_id}",
        "user_id": callback.from_user.id, "audio": mode == "audio",
        "document": mode == "document",
    })
    await callback.message.reply(
        f"🎚 Elige la calidad del {'audio' if mode == 'audio' else 'video'}:",
        reply_markup=_quality_keyboard(token, mode == "audio"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("media:audioq:") | F.data.startswith("media:videoq:"))
async def choose_quality(callback: CallbackQuery):
    parts = callback.data.split(":")
    token, quality = parts[2], parts[3]
    request = MEDIA_REQUESTS.pop(token, None)
    if not request:
        await callback.answer("Esta selección venció. Inicia otra búsqueda.", show_alert=True)
        return
    if request["user_id"] != callback.from_user.id:
        _remember_request(MEDIA_REQUESTS, token, request)
        await callback.answer("Esta descarga pertenece a otra persona.", show_alert=True)
        return
    await callback.answer("Descarga iniciada")
    await _send_download(callback.message, request["query"], audio=request["audio"],
                         document=request["document"], quality=quality,
                         requester_id=callback.from_user.id, status_message=callback.message)


@router.callback_query(F.data.startswith("media:cancel:"))
async def cancel_download(callback: CallbackQuery):
    job_id = callback.data.rsplit(":", 1)[-1]
    if DOWNLOAD_OWNERS.get(job_id) != callback.from_user.id:
        await callback.answer("Esta descarga no te pertenece.", show_alert=True)
        return
    cancel_user_download(callback.from_user.id)
    await callback.answer("Cancelando…")


@router.callback_query(F.data.startswith("media:dismiss:"))
async def dismiss_media(callback: CallbackQuery):
    token = callback.data.rsplit(":", 1)[-1]
    request = MEDIA_REQUESTS.get(token)
    if request and request.get("user_id") != callback.from_user.id:
        await callback.answer("Este menú pertenece a otra persona.", show_alert=True)
        return
    MEDIA_REQUESTS.pop(token, None)
    await callback.message.edit_text("✅ Operación cancelada.")
    await callback.answer()


@router.callback_query(F.data.startswith("media:direct:") | F.data.startswith("media:retry:"))
async def direct_or_retry_download(callback: CallbackQuery):
    token = callback.data.rsplit(":", 1)[-1]
    request = MEDIA_REQUESTS.pop(token, None)
    if not request:
        await callback.answer("Esta selección ya venció.", show_alert=True)
        return
    if request["user_id"] != callback.from_user.id:
        _remember_request(MEDIA_REQUESTS, token, request)
        await callback.answer("Esta descarga pertenece a otra persona.", show_alert=True)
        return
    await callback.answer("Descarga iniciada")
    await _send_download(
        callback.message, request["query"], audio=request.get("audio", False),
        document=request.get("document", False), quality=request.get("quality", "720"),
        requester_id=callback.from_user.id, status_message=callback.message,
        title_override=request.get("title_override"),
    )


async def _send_tiktok_carousel(message: Message, request: dict):
    images = request.get("images") or []
    work = Path(tempfile.mkdtemp(prefix="doxertube_carousel_"))
    user_id = request["user_id"]
    if user_id in ACTIVE_DOWNLOADS:
        await message.edit_text("⏳ Ya tienes otra descarga activa. Cancélala o espera que termine.")
        shutil.rmtree(work, ignore_errors=True)
        return
    job_id = secrets.token_hex(4)
    ACTIVE_DOWNLOADS[user_id] = job_id
    DOWNLOAD_OWNERS[job_id] = user_id
    cancel = InlineKeyboardBuilder()
    cancel.button(text="❌ Cancelar descarga", callback_data=f"media:cancel:{job_id}")
    deadline = monotonic() + MAX_DOWNLOAD_SECONDS
    try:
        await message.edit_text(f"📥 Descargando carrusel · 0/{len(images)}…", reply_markup=cancel.as_markup())
        paths = []
        for index, url in enumerate(images, 1):
            if monotonic() > deadline:
                raise asyncio.TimeoutError("El carrusel excedió el tiempo máximo")
            if job_id in CANCELLED_DOWNLOADS:
                raise DownloadCancelled()
            path = work / f"foto_{index:02d}.jpg"
            await asyncio.to_thread(_download_remote_file, url, path)
            paths.append(path)
            if index == len(images) or index % 3 == 0:
                await message.edit_text(
                    f"📥 Descargando carrusel · {index}/{len(images)}…",
                    reply_markup=cancel.as_markup(),
                )
        if job_id in CANCELLED_DOWNLOADS:
            raise DownloadCancelled()
        await message.edit_text("📤 Enviando las fotos a Telegram…", reply_markup=cancel.as_markup())
        for start in range(0, len(paths), 10):
            title = str(request.get("title") or "Carrusel de TikTok")[:900]
            album = MediaGroupBuilder(caption=(f"🖼 {title}" if start == 0 else None))
            for path in paths[start:start + 10]:
                album.add_photo(media=FSInputFile(path))
            await message.answer_media_group(media=album.build())
        await message.edit_text(f"✅ Carrusel descargado · {len(paths)} foto{'s' if len(paths) != 1 else ''}.")
    except DownloadCancelled:
        await message.edit_text("✅ Descarga cancelada.")
    except Exception as exc:
        logger.exception("Falló la descarga de un carrusel TikTok para el usuario %s", request.get("user_id"))
        await message.edit_text(
            f"❌ {_friendly_download_error(exc)} Puedes reintentar.",
            reply_markup=_retry_carousel_keyboard(request),
        )
    finally:
        ACTIVE_DOWNLOADS.pop(user_id, None)
        DOWNLOAD_OWNERS.pop(job_id, None)
        CANCELLED_DOWNLOADS.discard(job_id)
        shutil.rmtree(work, ignore_errors=True)


async def _send_instagram_gallery(message: Message, request: dict):
    urls = request.get("items") or []
    work = Path(tempfile.mkdtemp(prefix="doxertube_instagram_"))
    user_id = request["user_id"]
    if user_id in ACTIVE_DOWNLOADS:
        await message.edit_text("⏳ Ya tienes otra descarga activa. Cancélala o espera que termine.")
        shutil.rmtree(work, ignore_errors=True)
        return
    job_id = secrets.token_hex(4)
    ACTIVE_DOWNLOADS[user_id] = job_id
    DOWNLOAD_OWNERS[job_id] = user_id
    cancel = InlineKeyboardBuilder()
    cancel.button(text="❌ Cancelar descarga", callback_data=f"media:cancel:{job_id}")
    deadline = monotonic() + MAX_DOWNLOAD_SECONDS
    try:
        await message.edit_text(f"📥 Descargando publicación · 0/{len(urls)}…", reply_markup=cancel.as_markup())
        items = []
        for index, url in enumerate(urls, 1):
            if monotonic() > deadline:
                raise asyncio.TimeoutError("La publicación excedió el tiempo máximo")
            if job_id in CANCELLED_DOWNLOADS:
                raise DownloadCancelled()
            path, kind = await asyncio.to_thread(_download_instagram_item, url, work / f"archivo_{index:02d}")
            items.append((path, kind))
            await message.edit_text(
                f"📥 Descargando publicación · {index}/{len(urls)}…",
                reply_markup=cancel.as_markup(),
            )
        if job_id in CANCELLED_DOWNLOADS:
            raise DownloadCancelled()
        await message.edit_text("📤 Enviando la publicación a Telegram…", reply_markup=cancel.as_markup())
        if len(items) == 1:
            path, kind = items[0]
            if kind == "video":
                await message.answer_video(FSInputFile(path), caption="📸 Publicación de Instagram", supports_streaming=True)
            else:
                await message.answer_photo(FSInputFile(path), caption="📸 Publicación de Instagram")
        else:
            for start in range(0, len(items), 10):
                album = MediaGroupBuilder(caption="📸 Publicación de Instagram" if start == 0 else None)
                for path, kind in items[start:start + 10]:
                    if kind == "video":
                        album.add_video(media=FSInputFile(path), supports_streaming=True)
                    else:
                        album.add_photo(media=FSInputFile(path))
                await message.answer_media_group(media=album.build())
        await message.edit_text(f"✅ Publicación descargada · {len(items)} archivo{'s' if len(items) != 1 else ''}.")
    except DownloadCancelled:
        await message.edit_text("✅ Descarga cancelada.")
    except Exception as exc:
        logger.exception("Falló una publicación Instagram para el usuario %s", user_id)
        token = secrets.token_hex(4)
        _remember_request(MEDIA_REQUESTS, token, request)
        await message.edit_text(
            f"❌ {_friendly_download_error(exc)}",
            reply_markup=_instagram_keyboard(token, len(urls)),
        )
    finally:
        ACTIVE_DOWNLOADS.pop(user_id, None)
        DOWNLOAD_OWNERS.pop(job_id, None)
        CANCELLED_DOWNLOADS.discard(job_id)
        shutil.rmtree(work, ignore_errors=True)


def _retry_carousel_keyboard(request: dict):
    token = secrets.token_hex(4)
    _remember_request(MEDIA_REQUESTS, token, request)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔁 Reintentar", callback_data=f"media:carousel:{token}")
    builder.button(text="❌ Cerrar", callback_data=f"media:dismiss:{token}")
    builder.adjust(2)
    return builder.as_markup()


@router.callback_query(F.data.startswith("media:carousel:"))
async def download_tiktok_carousel(callback: CallbackQuery):
    token = callback.data.rsplit(":", 1)[-1]
    request = MEDIA_REQUESTS.pop(token, None)
    if not request:
        await callback.answer("Esta selección ya venció.", show_alert=True)
        return
    if request["user_id"] != callback.from_user.id:
        _remember_request(MEDIA_REQUESTS, token, request)
        await callback.answer("Este carrusel pertenece a otra persona.", show_alert=True)
        return
    await callback.answer("Descargando fotos…")
    await _send_tiktok_carousel(callback.message, request)


@router.callback_query(F.data.startswith("media:instagram:"))
async def download_instagram_gallery(callback: CallbackQuery):
    token = callback.data.rsplit(":", 1)[-1]
    request = MEDIA_REQUESTS.pop(token, None)
    if not request:
        await callback.answer("Esta selección ya venció.", show_alert=True)
        return
    if request["user_id"] != callback.from_user.id:
        _remember_request(MEDIA_REQUESTS, token, request)
        await callback.answer("Esta publicación pertenece a otra persona.", show_alert=True)
        return
    await callback.answer("Descargando publicación…")
    await _send_instagram_gallery(callback.message, request)


async def _tiktok_metadata(status, query, user_id):
    if user_id in ACTIVE_DOWNLOADS:
        raise RuntimeError("Ya tienes una descarga activa; usa /cancelar.")
    job_id = secrets.token_hex(4)
    ACTIVE_DOWNLOADS[user_id] = job_id
    DOWNLOAD_OWNERS[job_id] = user_id
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Cancelar", callback_data=f"media:cancel:{job_id}")
    try:
        await status.edit_text("🔎 Revisando TikTok…", reply_markup=kb.as_markup())
        for attempt in range(2):
            try:
                return await _stage(job_id, asyncio.wait_for(asyncio.to_thread(_fetch_tiktok_data, query), timeout=25))
            except DownloadCancelled:
                raise
            except Exception:
                if attempt:
                    raise
                await status.edit_text("🔄 TikTok tardó en responder. Reintentando…", reply_markup=kb.as_markup())
                await _stage(job_id, asyncio.sleep(0.5))
    finally:
        ACTIVE_DOWNLOADS.pop(user_id, None)
        DOWNLOAD_OWNERS.pop(job_id, None)
        CANCELLED_DOWNLOADS.discard(job_id)


async def _ask_video_quality(message: Message, query: str, user_id: int, document: bool = False):
    if _is_tiktok_url(query):
        status = await message.reply("🔎 Revisando la publicación de TikTok…")
        try:
            data = await _tiktok_metadata(status, query, user_id)
        except DownloadCancelled:
            await status.edit_text("✅ Descarga cancelada.")
            return
        except Exception:
            logger.exception("No se pudo analizar un enlace TikTok")
            token = secrets.token_hex(4)
            request = {"query": query, "user_id": user_id, "audio": False,
                       "document": document, "quality": "best"}
            _remember_request(MEDIA_REQUESTS, token, request)
            await status.edit_text(
                "❌ TikTok no respondió o el enlace ya no está disponible.",
                reply_markup=_retry_keyboard(request),
            )
            return
        token = secrets.token_hex(4)
        if data["kind"] == "carousel":
            _remember_request(MEDIA_REQUESTS, token, {
                **data, "query": query, "user_id": user_id,
                "audio": False, "document": document,
            })
            count = len(data["images"])
            await status.edit_text(
                f"🖼 <b>Carrusel de TikTok detectado</b>\nEncontré {count} foto{'s' if count != 1 else ''}.",
                parse_mode="HTML", reply_markup=_direct_keyboard(token, carousel=True),
            )
            return
        await _send_download(
            message, data["video_url"], audio=False, document=document,
            quality="best", requester_id=user_id, status_message=status,
            title_override=data.get("title") or "Video de TikTok",
            source_url=query,
        )
        return
    if _is_instagram_url(query):
        status = await message.reply("🔎 Revisando la publicación de Instagram…")
        try:
            urls = await asyncio.wait_for(asyncio.to_thread(_extract_instagram_urls, query), timeout=40)
        except Exception:
            logger.exception("No se pudo analizar un enlace Instagram")
            token = secrets.token_hex(4)
            request = {"query": query, "user_id": user_id, "audio": False,
                       "document": document, "quality": "best"}
            _remember_request(MEDIA_REQUESTS, token, request)
            await status.edit_text(
                "❌ No pude leer esa publicación. Si es privada, Instagram exige iniciar sesión.",
                reply_markup=_retry_keyboard(request),
            )
            return
        token = secrets.token_hex(4)
        _remember_request(MEDIA_REQUESTS, token, {
            "query": query, "items": urls, "user_id": user_id,
            "audio": False, "document": document,
        })
        await status.edit_text(
            f"📸 <b>Publicación de Instagram detectada</b>\n"
            f"Encontré {len(urls)} archivo{'s' if len(urls) != 1 else ''}.",
            parse_mode="HTML", reply_markup=_instagram_keyboard(token, len(urls)),
        )
        return
    token = secrets.token_hex(4)
    _remember_request(MEDIA_REQUESTS, token, {
        "query": query, "user_id": user_id, "audio": False, "document": document,
    })
    await message.reply("🎚 Elige la calidad del video:", reply_markup=_quality_keyboard(token, False))


async def _show_video_search(message: Message, query: str, mode: str):
    status = await message.reply("🔎 Buscando videos…")
    try:
        results = await asyncio.wait_for(asyncio.to_thread(_search_youtube, query), timeout=45)
        if not results:
            await status.edit_text("❌ No encontré videos con ese nombre.")
            return
        token = secrets.token_hex(4)
        if len(SEARCH_CACHE) >= 100:
            SEARCH_CACHE.pop(next(iter(SEARCH_CACHE)))
        _remember_request(SEARCH_CACHE, token, {"results": results, "user_id": message.from_user.id, "mode": mode})
        text, markup = _search_menu(results, token, 0, mode)
        await status.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except asyncio.TimeoutError:
        await status.edit_text("❌ YouTube tardó demasiado. Intenta nuevamente.")
    except Exception:
        await status.edit_text("❌ No pude buscar videos ahora. Intenta más tarde.")


@router.message(Command("playvideo", "ytmp4", "tiktok", "instagram", "facebook", "fb"))
async def video(message: Message, command: CommandObject):
    if not command.args:
        await message.reply("Envía un nombre o enlace después del comando.")
        return
    query = command.args.strip()
    if query.startswith(("http://", "https://")):
        await _ask_video_quality(message, query, message.from_user.id)
        return
    await _show_video_search(message, query, "video")


@router.message(Command("playdoc"))
async def video_document(message: Message, command: CommandObject):
    if not command.args:
        await message.reply("Usa /playdoc nombre o enlace")
        return
    query = command.args.strip()
    if query.startswith(("http://", "https://")):
        await _ask_video_quality(message, query, message.from_user.id, document=True)
        return
    await _show_video_search(message, query, "document")


async def download_history(message: Message):
    await _init_media_storage()
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute("""SELECT id,title,media_type,quality,status,cache_hit,created_at
            FROM download_history WHERE user_id=? ORDER BY id DESC LIMIT 10""",
            (message.from_user.id,))).fetchall()
    if not rows:
        await message.reply("📭 Todavía no tienes descargas registradas.")
        return
    icons = {"success": "✅", "failed": "❌", "cancelled": "🚫"}
    lines = ["📚 <b>Tus últimas descargas</b>", ""]
    keyboard = InlineKeyboardBuilder()
    button_count = 0
    for history_id, title, media_type, quality, status, cache_hit, created_at in rows:
        name = html.escape((title or "Sin título")[:55])
        fast = " ⚡" if cache_hit else ""
        lines.append(f"{icons.get(status, '•')} {name}\n{media_type} · {quality}{fast} · {created_at}")
        if status == "success" and button_count < 5:
            keyboard.button(text=f"🔁 {button_count + 1}. {(title or 'Archivo')[:25]}", callback_data=f"media:repeat:{history_id}")
            button_count += 1
    if button_count:
        keyboard.adjust(1)
    await message.reply("\n".join(lines), parse_mode="HTML", reply_markup=keyboard.as_markup() if button_count else None)


async def _history_item(history_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        return await (await db.execute("""SELECT query,media_type,quality,title,document
            FROM download_history WHERE id=? AND user_id=? AND status='success'""",
            (history_id, user_id))).fetchone()


@router.callback_query(F.data.startswith("media:repeat:"))
async def repeat_history(callback: CallbackQuery):
    history_id = int(callback.data.rsplit(":", 1)[1])
    item = await _history_item(history_id, callback.from_user.id)
    if not item:
        await callback.answer("Esa descarga no existe o no te pertenece.", show_alert=True); return
    query, media_type, quality, _, document = item
    await callback.answer("Añadiendo a la cola…")
    await _send_download(callback.message, query, audio=media_type == "audio", document=bool(document),
                         quality=quality or "720", requester_id=callback.from_user.id)


@router.callback_query(F.data.startswith("media:favorite:"))
async def add_favorite(callback: CallbackQuery):
    history_id = int(callback.data.rsplit(":", 1)[1])
    item = await _history_item(history_id, callback.from_user.id)
    if not item:
        await callback.answer("Esa descarga no existe o no te pertenece.", show_alert=True); return
    query, media_type, quality, title, document = item
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""INSERT OR IGNORE INTO media_favorites
            (user_id,query,media_type,quality,title,document) VALUES(?,?,?,?,?,?)""",
            (callback.from_user.id, query, media_type, quality, title, document))
        await db.commit()
    await callback.answer("⭐ Guardado en favoritos" if cursor.rowcount else "Ya estaba en favoritos", show_alert=True)


@router.message(Command("favoritos"))
async def favorites(message: Message):
    await _init_media_storage()
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute("""SELECT id,title,media_type,quality FROM media_favorites
            WHERE user_id=? ORDER BY id DESC LIMIT 15""", (message.from_user.id,))).fetchall()
    if not rows:
        await message.reply("⭐ Todavía no tienes favoritos. Usa el botón debajo de una descarga."); return
    builder = InlineKeyboardBuilder()
    lines = ["⭐ <b>Tus favoritos</b>", ""]
    for position, (favorite_id, title, media_type, quality) in enumerate(rows, 1):
        lines.append(f"{position}. {html.escape((title or 'Archivo')[:55])} · {media_type} {quality}")
        builder.button(text=f"▶️ {position}. {(title or 'Archivo')[:24]}", callback_data=f"favorite:repeat:{favorite_id}")
        builder.button(text="🗑", callback_data=f"favorite:delete:{favorite_id}")
    builder.adjust(2)
    await message.reply("\n".join(lines), parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("favorite:repeat:"))
async def repeat_favorite(callback: CallbackQuery):
    favorite_id = int(callback.data.rsplit(":", 1)[1])
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("""SELECT query,media_type,quality,document FROM media_favorites
            WHERE id=? AND user_id=?""", (favorite_id, callback.from_user.id))).fetchone()
    if not row:
        await callback.answer("Favorito no encontrado.", show_alert=True); return
    await callback.answer("Añadiendo a la cola…")
    await _send_download(callback.message, row[0], audio=row[1] == "audio", quality=row[2] or "720",
                         document=bool(row[3]), requester_id=callback.from_user.id)


@router.callback_query(F.data.startswith("favorite:delete:"))
async def delete_favorite(callback: CallbackQuery):
    favorite_id = int(callback.data.rsplit(":", 1)[1])
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM media_favorites WHERE id=? AND user_id=?", (favorite_id, callback.from_user.id)); await db.commit()
    await callback.answer("🗑 Favorito eliminado" if cursor.rowcount else "No encontrado", show_alert=True)
    try: await callback.message.delete()
    except Exception: pass


@router.message(Command("estadisticasbot"))
async def media_statistics(message: Message):
    await _init_media_storage()
    async with aiosqlite.connect(DB_PATH) as db:
        total = (await (await db.execute("SELECT COUNT(*) FROM download_history")).fetchone())[0]
        success = (await (await db.execute("SELECT COUNT(*) FROM download_history WHERE status='success'")).fetchone())[0]
        cache_hits = (await (await db.execute("SELECT COUNT(*) FROM download_history WHERE cache_hit=1")).fetchone())[0]
        audio = (await (await db.execute("SELECT COUNT(*) FROM download_history WHERE media_type='audio'")).fetchone())[0]
        users = (await (await db.execute("SELECT COUNT(DISTINCT user_id) FROM download_history")).fetchone())[0]
    rate = int(success * 100 / total) if total else 0
    filled = min(10, rate // 10)
    bar = "🟩" * filled + "⬜" * (10 - filled)
    await message.reply(
        "📊 <b>Estadísticas de NEXORA ONE</b>\n\n"
        f"📥 Solicitudes: <b>{total}</b>\n✅ Completadas: <b>{success}</b>\n"
        f"🎵 Audios: <b>{audio}</b>\n🎬 Videos: <b>{max(0, total-audio)}</b>\n"
        f"⚡ Desde caché: <b>{cache_hits}</b>\n👥 Usuarios: <b>{users}</b>\n\n"
        f"Éxito: {rate}%\n{bar}", parse_mode="HTML"
    )


@router.message(F.text.regexp(r"https?://\S+"))
async def automatic_download(message: Message):
    text = message.text or ""
    if any(host in text.lower() for host in ("tiktok.com", "instagram.com/", "youtu.be/", "youtube.com/shorts")):
        url = next((part for part in text.split() if part.startswith("http")), None)
        if url:
            await _ask_video_quality(message, url, message.from_user.id)
