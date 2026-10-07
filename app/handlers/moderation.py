from collections import defaultdict
from time import time
import re

from aiogram import Router, F
from aiogram.types import Message, ChatMemberUpdated, ChatPermissions, CallbackQuery
from aiogram.enums import ChatMemberStatus
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DEFAULT_CAPTCHA_TIMEOUT_MINUTES
from app.services.database import (
    get_settings,
    get_bad_words,
    add_warn,
    add_log,
    create_or_update_captcha,
    get_captcha,
    verify_captcha,
    delete_captcha,
    record_activity,
    get_activity_profile,
    mark_level_announced,
)
from app.services.filters import (
    contains_link,
    contains_bad_word,
    is_admin,
    generate_captcha,
    future_iso_minutes,
    is_expired,
    mute_until,
    full_unrestrict_permissions,
)
from app.services.admin_logs import send_admin_log
from app.services.templates import render_group_template
from app.services.group_tools import has_allowed_link, is_user_whitelisted

router = Router()

FLOOD_CACHE = defaultdict(list)
REPEAT_CACHE = defaultdict(list)
SLOW_MODE_CACHE = {}


def normalize_spam_text(text: str) -> str:
    normalized = (text or "").lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"(https?://\S+|www\.\S+|t\.me/\S+)", "[link]", normalized)
    return normalized[:160]


def captcha_keyboard(user_id: int, options: list[str]):
    builder = InlineKeyboardBuilder()
    for option in options:
        builder.button(
            text=option,
            callback_data=f"captcha:{user_id}:{option}"
        )
    builder.adjust(3)
    return builder.as_markup()


async def send_welcome(bot, chat, user, settings):
    text = await render_group_template(bot, chat, user, settings["welcome_text"])
    media_id = settings.get("welcome_media_id")
    media_type = settings.get("welcome_media_type")
    if media_id and media_type == "photo":
        await bot.send_photo(chat.id, media_id, caption=text[:1024])
    elif media_id and media_type == "animation":
        await bot.send_animation(chat.id, media_id, caption=text[:1024])
    else:
        await bot.send_message(chat.id, text)


@router.chat_member()
async def on_user_join(event: ChatMemberUpdated):
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    left = (
        old_status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}
        and new_status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
    )
    if left:
        user = event.new_chat_member.user
        settings = await get_settings(event.chat.id)
        if settings.get("farewell_enabled") and not user.is_bot:
            text = await render_group_template(event.bot, event.chat, user, settings["farewell_text"])
            await add_log(event.chat.id, "USER_LEFT", user_id=user.id)
            await event.bot.send_message(event.chat.id, text)
        return

    joined = (
        old_status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
        and new_status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}
    )

    if not joined:
        return

    user = event.new_chat_member.user
    settings = await get_settings(event.chat.id)

    if settings.get("approval_enabled"):
        try:
            await event.bot.restrict_chat_member(event.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
        except Exception:
            pass
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Aprobar", callback_data=f"approve:yes:{user.id}")
        builder.button(text="❌ Rechazar", callback_data=f"approve:no:{user.id}")
        await event.bot.send_message(
            event.chat.id,
            f"👋 <b>Nuevo miembro pendiente</b>\n\n{user.full_name}\nID: <code>{user.id}</code>\n\nUn administrador debe aprobar su ingreso.",
            parse_mode="HTML", reply_markup=builder.as_markup())
        await add_log(event.chat.id, "MEMBER_PENDING_APPROVAL", user_id=user.id)
        return

    if settings["captcha_enabled"]:
        question, answer, options = generate_captcha()
        expires_at = future_iso_minutes(DEFAULT_CAPTCHA_TIMEOUT_MINUTES)

        await create_or_update_captcha(
            chat_id=event.chat.id,
            user_id=user.id,
            question=question,
            answer=answer,
            expires_at=expires_at
        )

        try:
            await event.bot.restrict_chat_member(
                chat_id=event.chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False),
            )
        except Exception:
            pass

        await add_log(
            event.chat.id,
            "CAPTCHA_CREATED",
            user_id=user.id,
            reason=f"question={question}"
        )

        await event.bot.send_message(
            event.chat.id,
            (
                f"🛡 Verificación para {user.full_name}\n\n"
                f"Resuelve este captcha tocando un botón:\n"
                f"👉 {question}\n\n"
                f"Tienes {DEFAULT_CAPTCHA_TIMEOUT_MINUTES} minutos."
            ),
            reply_markup=captcha_keyboard(user.id, options)
        )
        return

    await add_log(event.chat.id, "USER_JOIN", user_id=user.id)
    await send_welcome(event.bot, event.chat, user, settings)


@router.callback_query(F.data.startswith("approve:"))
async def approval_callback(callback: CallbackQuery):
    if not callback.message or not await is_admin(callback.bot, callback.message.chat.id, callback.from_user.id):
        await callback.answer("Solo administradores.", show_alert=True); return
    _, decision, target_text = callback.data.split(":")
    target_id = int(target_text); chat_id = callback.message.chat.id
    try:
        member = await callback.bot.get_chat_member(chat_id, target_id)
        name = member.user.full_name
        if decision == "yes":
            await callback.bot.restrict_chat_member(chat_id, target_id, permissions=full_unrestrict_permissions())
            settings = await get_settings(chat_id)
            await callback.message.edit_text(f"✅ {name} fue aprobado por {callback.from_user.full_name}.")
            await add_log(chat_id, "MEMBER_APPROVED", user_id=target_id, admin_id=callback.from_user.id)
            await send_welcome(callback.bot, callback.message.chat, member.user, settings)
        else:
            await callback.bot.ban_chat_member(chat_id, target_id)
            await callback.message.edit_text(f"❌ {name} fue rechazado por {callback.from_user.full_name}.")
            await add_log(chat_id, "MEMBER_REJECTED", user_id=target_id, admin_id=callback.from_user.id)
        await callback.answer("Acción aplicada")
    except Exception as exc:
        await callback.answer("No pude aplicar la acción. Revisa mis permisos.", show_alert=True)


@router.callback_query(F.data.startswith("captcha:"))
async def captcha_callback(callback: CallbackQuery):
    if not callback.message or not callback.from_user:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Captcha inválido.", show_alert=True)
        return

    target_user_id = int(parts[1])
    selected_answer = parts[2]
    chat_id = callback.message.chat.id

    if callback.from_user.id != target_user_id:
        await callback.answer("Este captcha no es para ti.", show_alert=True)
        return

    captcha = await get_captcha(chat_id, callback.from_user.id)
    if not captcha:
        await callback.answer("No tienes captcha pendiente.", show_alert=True)
        return

    if captcha["verified"]:
        await callback.answer("Ya estás verificado.")
        return

    if is_expired(captcha["expires_at"]):
        try:
            await callback.bot.ban_chat_member(chat_id, callback.from_user.id)
            await callback.bot.unban_chat_member(chat_id, callback.from_user.id, only_if_banned=True)
        except Exception:
            pass

        await delete_captcha(chat_id, callback.from_user.id)
        await add_log(chat_id, "CAPTCHA_EXPIRED", user_id=callback.from_user.id)

        try:
            await callback.message.edit_text(
                f"⌛ El captcha de {callback.from_user.full_name} expiró."
            )
        except Exception:
            pass

        await callback.answer("Tu captcha expiró.", show_alert=True)
        return

    if selected_answer != captcha["answer"]:
        await add_log(chat_id, "CAPTCHA_FAILED", user_id=callback.from_user.id, reason=f"answer={selected_answer}")
        await callback.answer("❌ Respuesta incorrecta. Prueba otra vez.", show_alert=True)
        return

    await verify_captcha(chat_id, callback.from_user.id)
    await delete_captcha(chat_id, callback.from_user.id)

    try:
        await callback.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=callback.from_user.id,
            permissions=full_unrestrict_permissions(),
        )
    except Exception:
        pass

    settings = await get_settings(chat_id)

    await add_log(chat_id, "CAPTCHA_VERIFIED", user_id=callback.from_user.id)

    try:
        await callback.message.edit_text(
            f"✅ {callback.from_user.full_name} verificado correctamente."
        )
    except Exception:
        pass

    await callback.answer("Verificación completada")
    await send_welcome(callback.bot, callback.message.chat, callback.from_user, settings)


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def moderate_messages(message: Message):
    if not message.from_user:
        return

    messages = await record_activity(message.chat.id, message.from_user.id)
    level = messages // 25 + 1
    if messages and messages % 25 == 0 and await mark_level_announced(message.chat.id, message.from_user.id, level):
        _, _, role = await get_activity_profile(message.chat.id, message.from_user.id)
        await message.answer(
            f"🎉 {message.from_user.full_name} subió al <b>nivel {level}</b>!"
            + (f"\n🎖 Nuevo rol: <b>{role}</b>" if role else ""), parse_mode="HTML")

    if await is_admin(message.bot, message.chat.id, message.from_user.id):
        return

    if await is_user_whitelisted(message.chat.id, message.from_user.id):
        return

    text = message.text or message.caption or ""
    settings = await get_settings(message.chat.id)

    slow_seconds = settings.get("slow_mode_seconds", 0)
    if slow_seconds:
        key = (message.chat.id, message.from_user.id)
        now = time()
        previous = SLOW_MODE_CACHE.get(key, 0)
        if now - previous < slow_seconds:
            try:
                await message.delete()
            except Exception:
                pass
            remaining = max(1, int(slow_seconds - (now - previous)))
            await message.answer(f"🐢 {message.from_user.full_name}, espera {remaining}s antes de enviar otro mensaje.")
            return
        SLOW_MODE_CACHE[key] = now

    entities = list(message.entities or []) + list(message.caption_entities or [])
    mention_count = sum(1 for entity in entities if entity.type in {"mention", "text_mention"})
    mention_count = max(mention_count, len(re.findall(r"(?<!\w)@[A-Za-z0-9_]{5,}", text)))
    if mention_count > settings.get("mention_limit", 5):
        try:
            await message.delete()
        except Exception:
            pass
        warns = await add_warn(message.chat.id, message.from_user.id)
        await add_log(message.chat.id, "MENTION_SPAM", user_id=message.from_user.id,
                      reason=f"mentions={mention_count} | warns={warns}")
        await send_admin_log(message.bot, message.chat.id, "MENTION_SPAM", message.from_user.id,
                             detail=f"menciones={mention_count}, warns={warns}")
        mute_minutes = None
        if warns >= settings["warn_limit"]:
            mute_minutes = settings["auto_mute_minutes"]
        elif settings.get("progressive_sanctions") and warns == 2:
            mute_minutes = 10
        if mute_minutes:
            try:
                await message.bot.restrict_chat_member(
                    chat_id=message.chat.id, user_id=message.from_user.id,
                    permissions=ChatPermissions(can_send_messages=False), until_date=mute_until(mute_minutes)
                )
            except Exception:
                pass
        await message.answer(
            f"🚫 {message.from_user.full_name}, demasiadas menciones. Warns: {warns}"
            + (f" · mute {mute_minutes} min" if mute_minutes else "")
        )
        return

    if settings["anti_link"] and contains_link(text) and not await has_allowed_link(message.chat.id, text):
        try:
            await message.delete()
        except Exception:
            pass

        warns = await add_warn(message.chat.id, message.from_user.id)
        await add_log(
            message.chat.id,
            "DELETE_LINK",
            user_id=message.from_user.id,
            reason=f"warns={warns}"
        )
        await send_admin_log(message.bot, message.chat.id, "DELETE_LINK", message.from_user.id,
                             detail=f"warns={warns}")

        if warns >= settings["warn_limit"]:
            try:
                await message.bot.restrict_chat_member(
                    chat_id=message.chat.id,
                    user_id=message.from_user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=mute_until(settings["auto_mute_minutes"])
                )
            except Exception:
                pass

            await add_log(
                message.chat.id,
                "AUTO_MUTE_BY_LINK_WARNS",
                user_id=message.from_user.id,
                reason=f"{settings['auto_mute_minutes']} min"
            )

            await message.answer(
                f"🚫 {message.from_user.full_name}, no se permiten enlaces.\n"
                f"Has llegado al límite de warns y quedas silenciado por "
                f"{settings['auto_mute_minutes']} minutos."
            )
            return

        await message.answer(
            f"🚫 {message.from_user.full_name}, no se permiten enlaces.\n"
            f"Warns actuales: {warns}"
        )
        return

    letters = [character for character in text if character.isalpha()]
    uppercase_ratio = (sum(character.isupper() for character in letters) / len(letters)) if letters else 0
    if settings["antiflood"] and len(letters) >= 15 and uppercase_ratio >= 0.80:
        try:
            await message.delete()
        except Exception:
            pass
        warns = await add_warn(message.chat.id, message.from_user.id)
        await add_log(message.chat.id, "EXCESSIVE_CAPS", user_id=message.from_user.id,
                      reason=f"uppercase={uppercase_ratio:.0%} | warns={warns}")
        await send_admin_log(message.bot, message.chat.id, "EXCESSIVE_CAPS", message.from_user.id,
                             detail=f"mayúsculas={uppercase_ratio:.0%}, warns={warns}")
        await message.answer(
            f"🔠 {message.from_user.full_name}, evita escribir mensajes completos en mayúsculas.\nWarns: {warns}")
        return

    bad_words = await get_bad_words(message.chat.id)
    matched = contains_bad_word(text, bad_words)

    if matched:
        try:
            await message.delete()
        except Exception:
            pass

        warns = await add_warn(message.chat.id, message.from_user.id)
        await add_log(
            message.chat.id,
            "DELETE_BAD_WORD",
            user_id=message.from_user.id,
            reason=f"word={matched} | warns={warns}"
        )
        await send_admin_log(message.bot, message.chat.id, "DELETE_BAD_WORD", message.from_user.id,
                             detail=f"palabra={matched}, warns={warns}")

        if warns >= settings["warn_limit"]:
            try:
                await message.bot.restrict_chat_member(
                    chat_id=message.chat.id,
                    user_id=message.from_user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=mute_until(settings["auto_mute_minutes"])
                )
            except Exception:
                pass

            await add_log(
                message.chat.id,
                "AUTO_MUTE_BY_BAD_WORD_WARNS",
                user_id=message.from_user.id,
                reason=f"{settings['auto_mute_minutes']} min"
            )

            await message.answer(
                f"🧹 {message.from_user.full_name}, mensaje eliminado por palabra prohibida: {matched}.\n"
                f"Has llegado al límite de warns y quedas silenciado por "
                f"{settings['auto_mute_minutes']} minutos."
            )
            return

        await message.answer(
            f"🧹 {message.from_user.full_name}, mensaje eliminado por palabra prohibida: {matched}.\n"
            f"Warns actuales: {warns}"
        )
        return

    if settings["antiflood"]:
        key = f"{message.chat.id}:{message.from_user.id}"
        now = time()

        FLOOD_CACHE[key].append(now)
        window = settings["flood_window_seconds"]
        FLOOD_CACHE[key] = [t for t in FLOOD_CACHE[key] if now - t <= window]

        if len(FLOOD_CACHE[key]) > settings["flood_max_messages"]:
            try:
                await message.delete()
            except Exception:
                pass

            warns = await add_warn(message.chat.id, message.from_user.id)
            await add_log(
                message.chat.id,
                "FLOOD_DETECTED",
                user_id=message.from_user.id,
                reason=f"warns={warns}"
            )
            await send_admin_log(message.bot, message.chat.id, "FLOOD_DETECTED", message.from_user.id,
                                 detail=f"warns={warns}")

            try:
                await message.bot.restrict_chat_member(
                    chat_id=message.chat.id,
                    user_id=message.from_user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=mute_until(1)
                )
            except Exception:
                pass

            if warns >= settings["warn_limit"]:
                try:
                    await message.bot.restrict_chat_member(
                        chat_id=message.chat.id,
                        user_id=message.from_user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=mute_until(settings["auto_mute_minutes"])
                    )
                except Exception:
                    pass

                await add_log(
                    message.chat.id,
                    "AUTO_MUTE_BY_FLOOD_WARNS",
                    user_id=message.from_user.id,
                    reason=f"{settings['auto_mute_minutes']} min"
                )

                await message.answer(
                    f"⚡ {message.from_user.full_name}, flood detectado.\n"
                    f"Has llegado al límite de warns y quedas silenciado por "
                    f"{settings['auto_mute_minutes']} minutos."
                )
                return

            await message.answer(
                f"⚠️ {message.from_user.full_name}, baja la velocidad.\n"
                f"Flood detectado. Warns actuales: {warns}"
            )
            return

    normalized_text = normalize_spam_text(text)
    if normalized_text and len(normalized_text) >= 8:
        key = f"{message.chat.id}:{message.from_user.id}:{normalized_text}"
        now = time()
        REPEAT_CACHE[key].append(now)
        REPEAT_CACHE[key] = [t for t in REPEAT_CACHE[key] if now - t <= 45]

        if len(REPEAT_CACHE[key]) >= 3:
            try:
                await message.delete()
            except Exception:
                pass

            warns = await add_warn(message.chat.id, message.from_user.id)
            await add_log(
                message.chat.id,
                "REPEAT_SPAM_DETECTED",
                user_id=message.from_user.id,
                reason=f"warns={warns} | text={normalized_text[:60]}"
            )
            await send_admin_log(message.bot, message.chat.id, "REPEAT_SPAM_DETECTED",
                                 message.from_user.id, detail=f"warns={warns}")

            REPEAT_CACHE[key].clear()

            if warns >= settings["warn_limit"]:
                try:
                    await message.bot.restrict_chat_member(
                        chat_id=message.chat.id,
                        user_id=message.from_user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=mute_until(settings["auto_mute_minutes"])
                    )
                except Exception:
                    pass

                await add_log(
                    message.chat.id,
                    "AUTO_MUTE_BY_REPEAT_SPAM_WARNS",
                    user_id=message.from_user.id,
                    reason=f"{settings['auto_mute_minutes']} min"
                )

                await message.answer(
                    f"♻️ {message.from_user.full_name}, detecté mensajes repetidos.\n"
                    f"Has llegado al límite de warns y quedas silenciado por "
                    f"{settings['auto_mute_minutes']} minutos."
                )
                return

            await message.answer(
                f"♻️ {message.from_user.full_name}, evita repetir el mismo mensaje.\n"
                f"Warns actuales: {warns}"
            )
