import asyncio
import secrets
import time
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config import OWNER_USER_ID
from app.services import bans
from app.services.user_directory import resolve_username

router = Router()
pending = {}
lock = asyncio.Lock()

async def sync_account(uid, blocked):
    from nexora.comandos.utils import API_BASE, fetch_api_json_async
    if not API_BASE:
        return "⚠️ Web sin conectar; sanción guardada en el bot."
    path = "/internal/admin/register-ban" if blocked else "/internal/admin/user-action"
    status, _ = await fetch_api_json_async(path, method="POST", payload={"ID_TG": str(uid), "action": "ban" if blocked else "unban", "actor": str(OWNER_USER_ID)})
    return "" if status == 200 or (not blocked and status == 404) else "⚠️ No pude sincronizar el estado con la web; repite la operación cuando esté disponible."

async def target(message):
    parts = (message.text or "").split(maxsplit=2)
    reply = message.reply_to_message
    if reply and reply.from_user:
        return reply.from_user.id, (message.text or "").partition(" ")[2].strip()
    if len(parts)<2: return None,""
    uid = int(parts[1]) if parts[1].isdigit() else await resolve_username(message.bot,message.chat.id,parts[1])
    return uid, parts[2].strip() if len(parts)>2 else ""

@router.message(Command("ban", "unban", "bangg", "unbangg"))
async def request_ban(message):
    if message.from_user.id != OWNER_USER_ID:
        await message.answer("Solo el dueño puede cambiar el acceso al bot o aplicar un ban global.")
        return
    action = message.text.split()[0].split("@")[0][1:]
    uid, reason = await target(message)
    if not uid or uid in (OWNER_USER_ID,message.bot.id):
        await message.answer(f"Uso: /{action} ID motivo, o responde a un mensaje. No se puede aplicar al dueño ni al bot.")
        return
    if action in {"ban","bangg"} and not reason:
        await message.answer("Indica el motivo del baneo.")
        return
    reason = reason[:500]
    now = time.monotonic()
    for key in list(pending):
        if pending[key][0] < now: pending.pop(key,None)
    key = secrets.token_hex(8)
    pending[key] = (now+300,message.chat.id,action,uid,reason)
    builder=InlineKeyboardBuilder()
    builder.button(text="Confirmar", callback_data=f"globalban:{key}")
    builder.button(text="Cancelar", callback_data=f"globalcancel:{key}")
    await message.answer(f"Confirmar /{action} para {uid}\nMotivo: {reason or 'Retirar sanción'}\n" + ("Afectará los grupos conocidos donde tenga permiso. Se informará cada resultado." if action.endswith("gg") else "Solo afecta el acceso al bot."), reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("globalcancel:"))
async def cancel(callback):
    if callback.from_user.id != OWNER_USER_ID: return
    pending.pop(callback.data.split(":")[1],None)
    await callback.answer("Cancelado")
    await callback.message.edit_reply_markup(reply_markup=None)

@router.callback_query(F.data.startswith("globalban:"))
async def execute(callback):
    if callback.from_user.id != OWNER_USER_ID: return
    if lock.locked():
        await callback.answer("Hay otra operación global en curso.",show_alert=True)
        return
    item=pending.get(callback.data.split(":")[1])
    if not item or item[0]<time.monotonic() or item[1]!=callback.message.chat.id:
        await callback.answer("Confirmación vencida. Repite el comando.",show_alert=True)
        return
    pending.pop(callback.data.split(":")[1],None)
    await callback.answer("Procesando")
    await callback.message.edit_reply_markup(reply_markup=None)
    _,_,action,uid,reason=item
    async with lock:
        if action in {"ban","bangg"}:
            await bans.set_ban(uid,reason,action=="bangg")
            warning = await sync_account(uid,True)
        elif action=="unban":
            current=await bans.banned(uid)
            if current and current[1]:
                await callback.message.answer("Tiene un ban global. Usa /unbangg para retirarlo sin dejar sanciones pendientes.")
                return
            await bans.clear_ban(uid)
            warning = await sync_account(uid,False)
        if action in {"ban","unban"}:
            await callback.message.answer(f"✅ /{action} aplicado a {uid}.\n{warning}")
            return
        results=[]
        for chat_id in await bans.targets(uid if action=="unbangg" else None):
            try:
                member=await callback.bot.get_chat_member(chat_id,callback.bot.id)
                if member.status not in ("administrator","creator") or (member.status!="creator" and not member.can_restrict_members):
                    raise ValueError("Sin permiso para restringir miembros")
                if action=="bangg":
                    target_member=await callback.bot.get_chat_member(chat_id,uid)
                    if target_member.status in ("administrator","creator"):
                        raise ValueError("El usuario es administrador del grupo")
                    await callback.bot.ban_chat_member(chat_id,uid)
                    await bans.record(uid,chat_id)
                else:
                    await callback.bot.unban_chat_member(chat_id,uid,only_if_banned=True)
                    await bans.record(uid,chat_id,remove=True)
                results.append(f"✅ {chat_id}")
                try:
                    await callback.bot.send_message(chat_id,f"{'⛔ Baneo' if action=='bangg' else '✅ Desbaneo'} global\nUsuario: {uid}\nMotivo: {reason or 'Sanción retirada por el dueño'}")
                except Exception:
                    results.append(f"⚠️ {chat_id}: aplicado, pero no pude enviar el aviso")
            except Exception as exc:
                results.append(f"❌ {chat_id}: {str(exc)[:180]}")
            await asyncio.sleep(0.1)
        if action=="unbangg" and not await bans.targets(uid):
            await bans.clear_ban(uid)
            warning = await sync_account(uid,False)
        elif action == "unbangg":
            warning = "⚠️ Se mantiene el bloqueo del bot hasta resolver los grupos pendientes."
        text=f"Resultado /{action} para {uid}\n"+"\n".join(results or ["No hay grupos registrados para esta operación."])
        if warning:
            text += "\n" + warning
        for offset in range(0,len(text),3500):
            await callback.bot.send_message(OWNER_USER_ID,text[offset:offset+3500])
