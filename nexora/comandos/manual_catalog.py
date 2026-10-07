import json
import os
import re
import time

from telegram import Update
from telegram.ext import ContextTypes

from nexora.comandos.admin_requests import create_request
from nexora.comandos.utils import configured_admin_ids, get_command_runtime_config, verificar_usuario

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE_PATH = os.path.join(BASE_DIR, "config.json")

CFG = {}
try:
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            CFG = json.load(f) or {}
except Exception:
    CFG = {}

BOT_NAME = (CFG.get("BOT_NAME") or CFG.get("NAME") or "NEXORA ONE").strip()
if BOT_NAME.upper() in {"SPIDERSYN", "#SPIDERSYN"}:
    BOT_NAME = "NEXORA ONE"
CMDS = CFG.get("CMDS", {}) or {}
ERRS = CFG.get("ERRORCONSULTA", {}) or {}
ADMIN_IDS = configured_admin_ids()

NOCRED_TXT = ERRS.get("NOCREDITSTXT") or "[❗] No tienes créditos suficientes."
NOCRED_FT = (ERRS.get("NOCREDITSFT") or "").strip() or None
PLAN_LEVELS = {"FREE": 0, "BASICO": 1, "STANDARD": 2, "PREMIUM": 3}
PLAN_LABELS = {"FREE": "Libre", "BASICO": "Básico", "STANDARD": "Standard", "PREMIUM": "Premium"}


def _extract_command_slug(message_text: str | None) -> str:
    text = (message_text or "").strip()
    if not text.startswith("/"):
        return ""
    command = text.split()[0][1:]
    return command.split("@", 1)[0].strip().lower()


def _extract_args(message_text: str | None) -> list[str]:
    text = (message_text or "").strip()
    if not text:
        return []
    parts = text.split()
    return parts[1:]


def _category_loader_keys(category_slug: str | None) -> tuple[str | None, str | None]:
    slug = (category_slug or "").strip().upper()
    if not slug:
        return None, None
    return f"FT_{slug}", f"TXT_{slug}"


def _loader_assets(command_slug: str, category_slug: str | None) -> tuple[str | None, str]:
    command_key = command_slug.strip().upper()
    ft_key = f"FT_{command_key}"
    txt_key = f"TXT_{command_key}"
    loading_ft = (CMDS.get(ft_key) or "").strip() or None
    loading_txt = (CMDS.get(txt_key) or "").strip()

    if loading_ft or loading_txt:
        return loading_ft, (loading_txt or "Consultando…").strip()

    cat_ft_key, cat_txt_key = _category_loader_keys(category_slug)
    if cat_ft_key:
        loading_ft = (CMDS.get(cat_ft_key) or "").strip() or None
        loading_txt = (CMDS.get(cat_txt_key) or "").strip()
        if loading_ft or loading_txt:
            return loading_ft, (loading_txt or "Consultando…").strip()

    return None, "Consultando…"


def _parse_command_meta(command_cfg: dict) -> dict:
    direct_validation = command_cfg.get("validation")
    if isinstance(direct_validation, dict):
        return {"info": (command_cfg.get("description") or "").strip(), "validation": direct_validation}
    raw = (command_cfg.get("description") or "").strip()
    if not raw.startswith("{"):
        return {"info": raw, "validation": {}}
    try:
        data = json.loads(raw)
    except Exception:
        return {"info": raw, "validation": {}}
    if not isinstance(data, dict):
        return {"info": raw, "validation": {}}
    return {
        "info": str(data.get("info") or "").strip(),
        "validation": data.get("validation") if isinstance(data.get("validation"), dict) else {},
    }


def _normalize_plan(value: str | None) -> str:
    raw = (value or "").strip().upper()
    aliases = {
        "": "FREE",
        "NONE": "FREE",
        "PUBLICO": "FREE",
        "PÚBLICO": "FREE",
        "LIBRE": "FREE",
        "BASIC": "BASICO",
        "BÁSICO": "BASICO",
        "STANDAR": "STANDARD",
        "ESTANDAR": "STANDARD",
        "ESTÁNDAR": "STANDARD",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in PLAN_LEVELS else "FREE"


def _user_plan(info_usuario: dict) -> str:
    return _normalize_plan(
        info_usuario.get("PLAN")
        or info_usuario.get("plan")
        or info_usuario.get("ROL_TG")
        or info_usuario.get("rol_tg")
    )


def _is_privileged_user(info_usuario: dict) -> bool:
    role = (
        info_usuario.get("ROL_TG")
        or info_usuario.get("ROL")
        or info_usuario.get("role")
        or info_usuario.get("rol")
        or ""
    )
    return str(role).strip().upper() in {"FUNDADOR", "DUEÑO", "DUENO", "OWNER", "ADMIN", "COFUNDADOR"}


def _plan_block_message(command: str, required_plan: str, current_plan: str) -> str:
    required_label = PLAN_LABELS.get(required_plan, required_plan)
    current_label = PLAN_LABELS.get(current_plan, current_plan)
    return (
        "🔒 Acceso reservado\n\n"
        f"El comando /{command} requiere plan {required_label} o superior.\n"
        f"Tu plan actual es {current_label}.\n\n"
        "Usa /buy para subir de rango y activar este comando."
    )


def _antispam_seconds(info_usuario: dict) -> int:
    raw = (
        info_usuario.get("ANTISPAM")
        or info_usuario.get("anti_spam")
        or info_usuario.get("antispam")
        or info_usuario.get("ANTI_SPAM")
        or 0
    )
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 0


def _check_request_cooldown(context: ContextTypes.DEFAULT_TYPE, user_id: int, info_usuario: dict) -> str | None:
    if user_id in ADMIN_IDS or _is_privileged_user(info_usuario):
        return None
    cooldown = _antispam_seconds(info_usuario)
    if cooldown <= 0:
        return None
    bot_data = getattr(context.application, "bot_data", {}) if getattr(context, "application", None) else {}
    store = bot_data.setdefault("manual_command_cooldowns", {})
    key = str(user_id)
    now = time.monotonic()
    last = float(store.get(key) or 0)
    remaining = int(round(cooldown - (now - last)))
    if remaining > 0:
        return f"UPS, por favor espera el anti-spam de {cooldown} segundos.\nIntenta de nuevo en {remaining} s."
    store[key] = now
    return None


def _message_media_source(msg):
    if not msg:
        return None
    candidates = [msg, getattr(msg, "reply_to_message", None)]
    for item in candidates:
        if not item:
            continue
        if getattr(item, "photo", None):
            return item
        if getattr(item, "document", None):
            return item
    return None


def _validate_args(command_slug: str, command_cfg: dict, args: list[str], msg=None) -> str | None:
    meta = _parse_command_meta(command_cfg)
    validation = meta.get("validation") or {}
    text = " ".join(args).strip()
    usage_hint = (command_cfg.get("usage_hint") or f"/{command_slug} <datos>").strip()
    empty_message = validation.get("empty_message") or f"Por favor, proporciona los datos después de /{command_slug}."
    invalid_message = validation.get("invalid_message") or f"Por favor, usa el formato válido: {usage_hint}"
    kind = (validation.get("type") or "none").strip().lower()
    if kind in {"photo", "media", "photo_text", "media_text"}:
        if not _message_media_source(msg):
            return validation.get("empty_message") or (
                f"Envía una foto junto con /{command_slug} o responde a una foto con /{command_slug}."
            )
        if kind in {"photo", "media"}:
            return None
        if not text:
            return validation.get("empty_message") or (
                f"Envía la foto y agrega los datos después de /{command_slug}."
            )
        kind = "none"
    if not text:
        return empty_message
    if kind in {"", "none"}:
        return None
    if kind in {"digits", "number"} and not text.isdigit():
        return invalid_message
    if kind == "regex" and not (validation.get("regex") or "").strip():
        return None
    if kind == "letters":
        compact = text.replace(" ", "")
        if not compact.isalpha():
            return invalid_message
    if kind == "dni":
        if not (text.isdigit() and len(text) == 8):
            return validation.get("invalid_message") or "Por favor, introduce un número de DNI válido (8 dígitos)."
    exact_len = validation.get("length")
    try:
        exact_len = int(exact_len) if exact_len not in (None, "") else None
    except Exception:
        exact_len = None
    if exact_len and len(text) != exact_len:
        return invalid_message
    try:
        min_len = int(validation.get("min_length") or 0)
    except Exception:
        min_len = 0
    try:
        max_len = int(validation.get("max_length") or 0)
    except Exception:
        max_len = 0
    if min_len and len(text) < min_len:
        return invalid_message
    if max_len and len(text) > max_len:
        return invalid_message
    pattern = (validation.get("regex") or "").strip()
    if pattern:
        try:
            if not re.fullmatch(pattern, text):
                return invalid_message
        except re.error:
            pass
    return None


async def manual_catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not msg or not user:
        return

    command_slug = _extract_command_slug(getattr(msg, "text", "") or getattr(msg, "caption", ""))
    if not command_slug:
        return

    command_cfg = get_command_runtime_config(command_slug, 1)
    if not command_cfg.get("exists", False) or command_cfg.get("slug") != command_slug:
        await msg.reply_text("⚠️ Ese comando no está registrado en el catálogo.")
        return

    if chat and str(chat.type).lower() != "private":
        await msg.reply_text(
            "⚠️ Este comando solo puede usarse por privado.",
            reply_to_message_id=msg.message_id,
        )
        return

    if not command_cfg.get("is_active", True):
        await msg.reply_text("⚠️ Este comando está desactivado temporalmente.")
        return

    args = list(getattr(context, "args", None) or _extract_args(getattr(msg, "text", "") or getattr(msg, "caption", "")))
    validation_error = _validate_args(command_slug, command_cfg, args, msg)
    if validation_error and not args:
        usage_hint = (command_cfg.get("usage_hint") or f"/{command_slug} <datos>").strip()
        description = (command_cfg.get("name") or command_slug.upper()).strip()
        await msg.reply_text(
            f"📌 <b>{BOT_NAME} • {description.upper()}</b>\n\n"
            f"{validation_error}\n\n"
            f"Uso: <code>{usage_hint}</code>",
            parse_mode="HTML",
            reply_to_message_id=msg.message_id,
        )
        return
    if validation_error:
        await msg.reply_text(validation_error, reply_to_message_id=msg.message_id)
        return

    valido, info_usuario = verificar_usuario(str(user.id))
    if not valido:
        await msg.reply_text("🚫 Tu cuenta no está activa o no existe.")
        return

    ilimitado = info_usuario.get("ilimitado", False)
    creditos = int(info_usuario.get("CREDITOS", 0))
    required_credits = int(command_cfg.get("cost", 1))
    required_plan = _normalize_plan(command_cfg.get("required_plan"))
    current_plan = _user_plan(info_usuario)

    if not _is_privileged_user(info_usuario) and PLAN_LEVELS[current_plan] < PLAN_LEVELS[required_plan]:
        await msg.reply_text(
            _plan_block_message(command_slug, required_plan, current_plan),
            reply_to_message_id=msg.message_id,
        )
        return

    cooldown_error = _check_request_cooldown(context, user.id, info_usuario)
    if cooldown_error:
        await msg.reply_text(cooldown_error, reply_to_message_id=msg.message_id)
        return

    if not ilimitado and creditos < required_credits:
        if NOCRED_FT:
            await msg.reply_photo(photo=NOCRED_FT, caption=NOCRED_TXT, parse_mode="HTML")
        else:
            await msg.reply_text(NOCRED_TXT, parse_mode="HTML")
        return

    loading_ft, loading_txt = _loader_assets(command_slug, command_cfg.get("category_slug"))
    status_message = None
    try:
        if loading_ft:
            status_message = await msg.reply_photo(photo=loading_ft, caption=loading_txt, parse_mode="HTML")
        else:
            status_message = await msg.reply_text(loading_txt, parse_mode="HTML")
    except Exception:
        pass

    await create_request(update, context, command_slug, cost=required_credits, status_message=status_message)
