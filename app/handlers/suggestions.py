import html
from collections import defaultdict
from time import monotonic

from nexora import async_db as aiosqlite
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DB_PATH, OWNER_USER_ID
from app.services.database import get_settings

router = Router()
LAST_SUGGESTION: dict[int, float] = defaultdict(float)
SUGGESTION_COOLDOWN = 10 * 60


class SuggestionForm(StatesGroup):
    text = State()
    confirm = State()
    owner_reply = State()


def suggestion_confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Enviar", callback_data="suggest:confirm")
    builder.button(text="❌ Cancelar", callback_data="suggest:cancel")
    builder.adjust(2)
    return builder.as_markup()


def owner_suggestion_keyboard(suggestion_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Responder", callback_data=f"suggest:reply:{suggestion_id}")
    builder.button(text="✅ Marcar revisada", callback_data=f"suggest:review:{suggestion_id}")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data == "suggest:start")
async def start_suggestion(callback: CallbackQuery, state: FSMContext):
    remaining = int(SUGGESTION_COOLDOWN - (monotonic() - LAST_SUGGESTION[callback.from_user.id]))
    if remaining > 0:
        await callback.answer(f"Podrás enviar otra sugerencia en {remaining // 60 + 1} min.", show_alert=True)
        return
    await state.set_state(SuggestionForm.text)
    await state.update_data(source_chat_id=callback.message.chat.id, source_title=callback.message.chat.title or "Chat privado")
    await callback.message.reply(
        "💡 <b>Nueva sugerencia</b>\n\nEscribe tu idea o mejora en un solo mensaje. Usa /cancelar para salir.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SuggestionForm.text, F.text)
async def receive_suggestion(message: Message, state: FSMContext):
    text = message.text.strip()
    if not 5 <= len(text) <= 1500:
        await message.reply("La sugerencia debe tener entre 5 y 1500 caracteres.")
        return
    await state.update_data(text=text)
    await state.set_state(SuggestionForm.confirm)
    await message.reply(
        f"💡 <b>Vista previa</b>\n\n{html.escape(text)}\n\n¿Deseas enviarla?",
        parse_mode="HTML",
        reply_markup=suggestion_confirm_keyboard(),
    )


@router.callback_query(F.data == "suggest:cancel")
async def cancel_suggestion(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("✅ Sugerencia cancelada.")
    await callback.answer()


@router.callback_query(F.data == "suggest:confirm")
async def confirm_suggestion(callback: CallbackQuery, state: FSMContext):
    if await state.get_state() != SuggestionForm.confirm.state:
        await callback.answer("Esta sugerencia ya venció.", show_alert=True)
        return
    data = await state.get_data()
    source_chat_id = data["source_chat_id"]
    source_title = data["source_title"]
    text = data["text"]
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO suggestions (user_id,source_chat_id,source_title,text) VALUES (?,?,?,?)",
            (callback.from_user.id, source_chat_id, source_title, text),
        )
        suggestion_id = cursor.lastrowid
        await db.commit()
    username = f"@{callback.from_user.username}" if callback.from_user.username else "Sin username"
    report = (
        f"💡 <b>Sugerencia #{suggestion_id}</b>\n\n"
        f"👤 {html.escape(callback.from_user.full_name)} ({html.escape(username)})\n"
        f"🆔 Usuario: <code>{callback.from_user.id}</code>\n"
        f"💬 Origen: {html.escape(source_title)}\n"
        f"🆔 Chat: <code>{source_chat_id}</code>\n\n"
        f"{html.escape(text)}"
    )
    delivered = False
    try:
        await callback.bot.send_message(
            OWNER_USER_ID, report, parse_mode="HTML",
            reply_markup=owner_suggestion_keyboard(suggestion_id),
        )
        delivered = True
    except Exception:
        pass
    if source_chat_id < 0:
        settings = await get_settings(source_chat_id)
        log_chat_id = settings.get("log_chat_id")
        if log_chat_id:
            try:
                await callback.bot.send_message(log_chat_id, report, parse_mode="HTML")
                delivered = True
            except Exception:
                pass
    await state.clear()
    if delivered:
        LAST_SUGGESTION[callback.from_user.id] = monotonic()
        await callback.message.edit_text(f"✅ Sugerencia #{suggestion_id} enviada. Consulta su estado con /miscasos.")
        await callback.answer("Enviada")
    else:
        await callback.message.edit_text("❌ No pude entregar la sugerencia. Intenta nuevamente más tarde.")
        await callback.answer("No se pudo enviar", show_alert=True)


@router.callback_query(F.data.startswith("suggest:review:"))
async def review_suggestion(callback: CallbackQuery):
    if callback.from_user.id != OWNER_USER_ID:
        await callback.answer("Solo el dueño puede revisar sugerencias.", show_alert=True)
        return
    suggestion_id = int(callback.data.rsplit(":", 1)[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE suggestions SET status='reviewed', reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
            (suggestion_id,),
        )
        await db.commit()
    await callback.message.edit_text(callback.message.html_text + "\n\n✅ <b>Revisada</b>", parse_mode="HTML")
    await callback.answer("Marcada como revisada")


@router.callback_query(F.data.startswith("suggest:reply:"))
async def prepare_owner_reply(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_USER_ID:
        await callback.answer("Solo el dueño puede responder.", show_alert=True)
        return
    suggestion_id = int(callback.data.rsplit(":", 1)[1])
    await state.set_state(SuggestionForm.owner_reply)
    await state.update_data(suggestion_id=suggestion_id)
    await callback.message.reply("💬 Escribe la respuesta para esta sugerencia. Usa /cancelar para salir.")
    await callback.answer()


@router.message(SuggestionForm.owner_reply, F.text)
async def send_owner_reply(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_USER_ID:
        await state.clear()
        return
    data = await state.get_data()
    suggestion_id = data["suggestion_id"]
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("SELECT user_id,source_chat_id FROM suggestions WHERE id=?", (suggestion_id,))).fetchone()
    await state.clear()
    if not row:
        await message.reply("❌ Ya no encuentro esa sugerencia.")
        return
    try:
        await message.bot.send_message(
            row[0],
            f"💬 <b>Respuesta a tu sugerencia #{suggestion_id}</b>\n\n{html.escape(message.text[:1500])}",
            parse_mode="HTML",
        )
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE suggestions SET status='answered', reviewed_at=CURRENT_TIMESTAMP WHERE id=?", (suggestion_id,))
            await db.execute("INSERT INTO case_replies(kind,case_id,chat_id,user_id,admin_id,text) VALUES('sugerencia',?,?,?,?,?)",
                             (suggestion_id, row[1], row[0], message.from_user.id, message.text[:1500]))
            await db.commit()
        await message.reply("✅ Respuesta enviada al usuario.")
    except Exception:
        await message.reply("❌ No pude escribirle al usuario; posiblemente bloqueó el bot.")
