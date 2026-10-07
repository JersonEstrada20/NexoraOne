import ast
import html
import operator
import random
from datetime import date
from time import monotonic

import asyncio
import io

from nexora import async_db as aiosqlite
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DB_PATH

router = Router()
COOLDOWNS: dict[tuple[int, str], float] = {}
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg}
SHOP = {
    "pico": ("⛏ Pico profesional", 150, "Aumenta 50% las ganancias al minar."),
    "cana": ("🎣 Caña reforzada", 150, "Aumenta 50% las ganancias al pescar."),
    "amuleto": ("🍀 Amuleto de suerte", 300, "Mejora la probabilidad de ganar en el casino."),
    "insignia": ("🏅 Insignia dorada", 500, "Objeto especial para coleccionar."),
    "cofre": ("🎁 Cofre misterioso", 250, "Coleccionable especial para tu inventario."),
    "corona": ("👑 Corona NEXORA ONE", 1000, "Distintivo exclusivo para tu cartera."),
}
MISSIONS = {
    "daily": {"trabajo": ("⛏ Trabaja 2 veces", "work", 2, 50), "casino": ("🎰 Juega 3 partidas", "casino", 3, 60), "recompensa": ("🎁 Reclama tu daily", "daily", 1, 40)},
    "weekly": {"trabajo": ("⛏ Trabaja 10 veces", "work", 10, 250), "casino": ("🎰 Juega 15 partidas", "casino", 15, 300), "recompensa": ("🎁 Reclama 5 recompensas", "daily", 5, 400)},
}


async def _animate(message: Message, frames: list[str], delay: float = 0.65):
    status = await message.reply(frames[0])
    for frame in frames[1:]:
        await asyncio.sleep(delay)
        try:
            await status.edit_text(frame)
        except Exception:
            pass
    return status


async def _is_registered(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            row = await (await db.execute("SELECT 1 FROM economy WHERE user_id=?", (user_id,))).fetchone()
        except aiosqlite.OperationalError:
            return False
    return row is not None


async def _init_user(user_id: int, name: str, chat_id: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS economy (
            user_id INTEGER PRIMARY KEY, name TEXT NOT NULL, coins INTEGER NOT NULL DEFAULT 100,
            xp INTEGER NOT NULL DEFAULT 0, reputation INTEGER NOT NULL DEFAULT 0, last_daily TEXT)""")
        await db.execute("INSERT OR IGNORE INTO economy(user_id,name) VALUES(?,?)", (user_id, name))
        await db.execute("UPDATE economy SET name=? WHERE user_id=?", (name, user_id))
        await db.execute("""CREATE TABLE IF NOT EXISTS economy_groups (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            PRIMARY KEY(chat_id, user_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER NOT NULL, item_key TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, item_key))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS economy_missions (
            user_id INTEGER NOT NULL, period TEXT NOT NULL, mission_key TEXT NOT NULL,
            period_key TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
            claimed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, period, mission_key, period_key))""")
        await db.execute("INSERT OR IGNORE INTO economy_groups(chat_id,user_id) VALUES(?,?)", (chat_id, user_id))
        await db.commit()


async def _user(user_id: int, name: str, chat_id: int = 0):
    await _init_user(user_id, name, chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM economy WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone()


async def _change(user_id: int, coins: int = 0, xp: int = 0, rep: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE economy SET coins=max(0,coins+?), xp=max(0,xp+?), reputation=max(0,reputation+?) WHERE user_id=?",
                         (coins, xp, rep, user_id))
        await db.commit()


async def _item_count(user_id: int, item_key: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_key=?", (user_id, item_key)
        )).fetchone()
        return row[0] if row else 0


def _level(xp: int) -> int:
    return int((xp / 100) ** 0.5) + 1


def _cooldown(user_id: int, action: str, seconds: int) -> int:
    key = (user_id, action)
    remaining = int(COOLDOWNS.get(key, 0) - monotonic())
    if remaining > 0:
        return remaining + 1
    COOLDOWNS[key] = monotonic() + seconds
    return 0


def _mission_period_key(period: str) -> str:
    today = date.today()
    return today.isoformat() if period == "daily" else f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"


async def _record_mission(user_id: int, action: str):
    async with aiosqlite.connect(DB_PATH) as db:
        for period, missions in MISSIONS.items():
            period_key = _mission_period_key(period)
            for key, (_, mission_action, target, _) in missions.items():
                if mission_action != action:
                    continue
                await db.execute("INSERT OR IGNORE INTO economy_missions(user_id,period,mission_key,period_key) VALUES(?,?,?,?)", (user_id, period, key, period_key))
                await db.execute("UPDATE economy_missions SET progress=min(progress+1,?) WHERE user_id=? AND period=? AND mission_key=? AND period_key=? AND claimed=0", (target, user_id, period, key, period_key))
        await db.commit()


async def register(message: Message):
    user = message.from_user
    if await _is_registered(user.id):
        await message.reply("ℹ️ Ya estás registrado. Usa /perfil para ver tu progreso.")
        return
    status = await _animate(message, ["📝 Creando tu cuenta…", "💾 Guardando tus datos…", "🎉 ¡Registro completado!"])
    await _init_user(user.id, user.full_name, message.chat.id)
    await status.edit_text("✅ Registro listo. Recibiste <b>S/ 100</b>. Usa /daily para tu premio diario.", parse_mode="HTML")


async def profile(message: Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    row = await _user(target.id, target.full_name, message.chat.id)
    crown = " 👑" if await _item_count(target.id, "corona") else ""
    caption = (
        f"💳 <b>Cartera de {html.escape(row['name'])}{crown}</b>\n\n"
        f"💵 Saldo: <b>S/ {row['coins']}</b>\n✨ Experiencia: <b>{row['xp']} XP</b>\n"
        f"🏅 Nivel: <b>{_level(row['xp'])}</b>\n🤝 Reputación: <b>{row['reputation']}</b>\n\n"
        "🎁 /daily · 🛍 /tienda · 🎒 /inventario"
    )
    try:
        photos = await message.bot.get_user_profile_photos(target.id, limit=1)
        if photos.total_count:
            await message.reply_photo(photos.photos[0][-1].file_id, caption=caption, parse_mode="HTML")
            return
    except Exception:
        pass
    await message.reply(caption, parse_mode="HTML")


def _profile_card(row, reputation: int, crown: bool) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (1000, 560), (13, 24, 40))
    draw = ImageDraw.Draw(image)
    for y in range(560):
        color = (18 + y // 18, 42 + y // 12, 70 + y // 8)
        draw.line((0, y, 1000, y), fill=color)
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 42)
        body_font = ImageFont.truetype("DejaVuSans.ttf", 28)
        small_font = ImageFont.truetype("DejaVuSans.ttf", 23)
    except OSError:
        title_font = body_font = small_font = ImageFont.load_default()
    level = _level(row["xp"])
    draw.rounded_rectangle((45, 40, 955, 515), radius=28, outline=(65, 190, 220), width=3, fill=(18, 32, 52))
    draw.text((80, 75), "DOXERTUBE · PERFIL", font=small_font, fill=(107, 220, 220))
    draw.text((80, 125), f"{row['name'][:28]}{'  👑' if crown else ''}", font=title_font, fill="white")
    draw.text((80, 220), f"S/ {row['coins']}", font=title_font, fill=(255, 216, 92))
    draw.text((80, 285), f"Nivel {level}   ·   {row['xp']} XP", font=body_font, fill=(230, 240, 250))
    draw.text((80, 345), f"Reputación: {reputation}", font=body_font, fill=(190, 210, 230))
    progress = row["xp"] % 100
    draw.rounded_rectangle((80, 425, 900, 455), radius=15, fill=(35, 57, 78))
    draw.rounded_rectangle((80, 425, 80 + int(820 * progress / 100), 455), radius=15, fill=(53, 205, 150))
    draw.text((80, 470), f"Progreso al nivel {level + 1}: {progress}%", font=small_font, fill=(170, 195, 215))
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


@router.message(Command("tarjeta", "card"))
async def profile_card(message: Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    row = await _user(target.id, target.full_name, message.chat.id)
    crown = await _item_count(target.id, "corona") > 0
    data = _profile_card(row, row["reputation"], crown)
    await message.answer_photo(BufferedInputFile(data, filename="perfil-doxertube.png"), caption="🎴 Tu tarjeta de perfil")


@router.message(Command("misiones"))
async def missions(message: Message):
    user = message.from_user
    await _user(user.id, user.full_name, message.chat.id)
    lines, builder = ["🎯 <b>Tus misiones</b>", ""], InlineKeyboardBuilder()
    async with aiosqlite.connect(DB_PATH) as db:
        for period, entries in MISSIONS.items():
            period_key = _mission_period_key(period)
            lines.append(f"<b>{'Hoy' if period == 'daily' else 'Esta semana'}</b>")
            for key, (label, _, target, reward) in entries.items():
                await db.execute("INSERT OR IGNORE INTO economy_missions(user_id,period,mission_key,period_key) VALUES(?,?,?,?)", (user.id, period, key, period_key))
                row = await (await db.execute("SELECT progress,claimed FROM economy_missions WHERE user_id=? AND period=? AND mission_key=? AND period_key=?", (user.id, period, key, period_key))).fetchone()
                progress, claimed = row
                status = "✅ Reclamada" if claimed else f"{progress}/{target}"
                lines.append(f"• {label}: <b>{status}</b> · S/ {reward}")
                if progress >= target and not claimed:
                    builder.button(text=f"🎁 Reclamar S/ {reward}", callback_data=f"mission:claim:{user.id}:{period}:{key}")
            lines.append("")
        await db.commit()
    builder.button(text="🔄 Actualizar", callback_data=f"mission:refresh:{user.id}")
    builder.adjust(1)
    await message.reply("\n".join(lines), parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("mission:claim:"))
async def claim_mission(callback: CallbackQuery):
    _, _, user_text, period, key = callback.data.split(":", 4)
    if callback.from_user.id != int(user_text) or period not in MISSIONS or key not in MISSIONS[period]:
        await callback.answer("Esta misión no te pertenece.", show_alert=True); return
    _, _, target, reward = MISSIONS[period][key]
    period_key = _mission_period_key(period)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE economy_missions SET claimed=1 WHERE user_id=? AND period=? AND mission_key=? AND period_key=? AND progress>=? AND claimed=0", (callback.from_user.id, period, key, period_key, target))
        if cursor.rowcount:
            await db.execute("UPDATE economy SET coins=coins+?,xp=xp+10 WHERE user_id=?", (reward, callback.from_user.id))
        await db.commit()
    await callback.answer(f"S/ {reward} reclamados" if cursor.rowcount else "Misión no disponible", show_alert=True)
    await callback.message.delete()


@router.callback_query(F.data.startswith("mission:refresh:"))
async def refresh_missions(callback: CallbackQuery):
    if callback.from_user.id != int(callback.data.rsplit(":", 1)[-1]):
        await callback.answer("Este menú pertenece a otra persona.", show_alert=True); return
    await callback.answer("Usa /misiones para ver el estado actualizado.")


@router.message(Command("daily", "dayli"))
async def daily(message: Message):
    user = message.from_user
    row = await _user(user.id, user.full_name, message.chat.id)
    today = date.today().isoformat()
    if row["last_daily"] == today:
        await message.reply("⏳ Ya reclamaste la recompensa de hoy.")
        return
    reward = random.randint(80, 160)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE economy SET coins=coins+?,xp=xp+25,last_daily=? WHERE user_id=? AND (last_daily IS NULL OR last_daily<>?)", (reward, today, user.id, today))
        await db.commit()
    if not cursor.rowcount:
        await message.reply("⏳ Ya reclamaste la recompensa de hoy.")
        return
    await _record_mission(user.id, "daily")
    status = await _animate(message, ["🎁 Buscando tu recompensa…", "✨ Abriendo el regalo…", "🪙 Contando tus soles…"])
    await status.edit_text(f"🎉 <b>Recompensa diaria</b>\n\n💵 S/ {reward}\n✨ 25 XP\n\nVuelve mañana.", parse_mode="HTML")


@router.message(Command("minar", "pescar"))
async def work(message: Message):
    user = message.from_user
    wait = _cooldown(user.id, "work", 60)
    if wait:
        await message.reply(f"⏳ Espera {wait} segundos antes de trabajar nuevamente.")
        return
    await _user(user.id, user.full_name, message.chat.id)
    mining = "minar" in (message.text or "").lower()
    if mining:
        status = await _animate(message, ["⛏ Entrando a la mina…", "🪨 Picando rocas…", "✨ Encontraste minerales…"])
    else:
        status = await _animate(message, ["🎣 Lanzando la caña…", "🌊 Esperando que pique…", "🐟 ¡Algo mordió el anzuelo!"])
    reward = random.randint(8, 35)
    if mining and await _item_count(user.id, "pico"):
        reward = int(reward * 1.5)
    if not mining and await _item_count(user.id, "cana"):
        reward = int(reward * 1.5)
    await _change(user.id, coins=reward, xp=10)
    await _record_mission(user.id, "work")
    await status.edit_text(f"{'⛏' if mining else '🎣'} <b>Trabajo terminado</b>\n\n💵 Ganaste S/ {reward}\n✨ 10 XP", parse_mode="HTML")


@router.message(Command("tragamonedas", "tragamoneda", "ruleta"))
async def casino(message: Message):
    user = message.from_user
    wait = _cooldown(user.id, "casino", 20)
    if wait:
        await message.reply(f"⏳ Espera {wait} segundos antes de volver a jugar.")
        return
    row = await _user(user.id, user.full_name, message.chat.id)
    bet = 10
    if row["coins"] < bet:
        await message.reply("❌ Necesitas al menos S/ 10.")
        return
    win_chance = 0.45 if await _item_count(user.id, "amuleto") else 0.35
    win = random.random() < win_chance
    delta = random.choice((20, 30, 50)) if win else -bet
    async with aiosqlite.connect(DB_PATH) as db:
        debit = await db.execute("UPDATE economy SET coins=coins+?,xp=xp+3 WHERE user_id=? AND coins>=?", (delta, user.id, bet))
        await db.commit()
    if not debit.rowcount:
        await message.reply("❌ Ya no tienes suficientes soles para apostar.")
        return
    await _record_mission(user.id, "casino")
    roulette = "ruleta" in (message.text or "").lower()
    if roulette:
        status = await _animate(message, ["🎡 Girando la ruleta…", "🔴 ⚫ 🔴 ⚫", "🟢 La bola está cayendo…"])
    else:
        status = await _animate(message, ["🎰 Girando…", "🍒 | ⭐ | 7️⃣", "7️⃣ | 🍒 | ⭐", "⭐ | ⭐ | …"])
    await status.edit_text(f"{'🎉 ¡Ganaste!' if win else '💥 Perdiste'} <b>S/ {abs(delta)}</b>\n✨ Recibiste 3 XP.", parse_mode="HTML")


@router.message(Command("rank", "rankcoins", "ranksoles", "ranknivel", "rankrep"))
async def ranking(message: Message):
    await _init_user(message.from_user.id, message.from_user.full_name, message.chat.id)
    field = "reputation" if "rep" in (message.text or "") else "xp" if "nivel" in (message.text or "") else "coins"
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            f"SELECT e.name,e.{field} FROM economy e JOIN economy_groups g ON g.user_id=e.user_id "
            f"WHERE g.chat_id=? ORDER BY e.{field} DESC LIMIT 10", (message.chat.id,)
        )).fetchall()
    unit = "S/ " if field == "coins" else ""
    await message.reply("🏆 Ranking de este grupo\n\n" + "\n".join(f"{i}. {name}: {unit}{value}" for i, (name, value) in enumerate(rows, 1)))


@router.message(Command("transferir", "pagar"))
async def transfer(message: Message, command: CommandObject):
    sender = message.from_user
    target_message = message.reply_to_message
    args = (command.args or "").split()
    if target_message and target_message.from_user:
        target_id, target_name = target_message.from_user.id, target_message.from_user.full_name
        amount_text = args[0] if args else ""
        target_is_bot = target_message.from_user.is_bot
    else:
        try:
            target_id, amount_text = int(args[0]), args[1]
            target_name, target_is_bot = f"Usuario {target_id}", False
        except (ValueError, IndexError):
            await message.reply("Responde con <code>/transferir cantidad</code> o usa <code>/transferir ID cantidad</code>.", parse_mode="HTML")
            return
    if target_id == sender.id or target_is_bot:
        await message.reply("❌ Selecciona otra persona que no sea un bot.")
        return
    try:
        amount = int(amount_text)
    except ValueError:
        amount = 0
    if amount < 1 or amount > 100000:
        await message.reply("Usa una cantidad entre S/ 1 y S/ 100000.")
        return
    await _init_user(sender.id, sender.full_name, message.chat.id)
    await _init_user(target_id, target_name, message.chat.id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("CREATE TABLE IF NOT EXISTS transfer_receipts (chat_id INTEGER, message_id INTEGER, user_id INTEGER, PRIMARY KEY(chat_id,message_id,user_id))")
        receipt = await db.execute("INSERT OR IGNORE INTO transfer_receipts VALUES (?,?,?)", (message.chat.id, message.message_id, sender.id))
        if not receipt.rowcount:
            await db.rollback()
            await message.reply("✅ Esta transferencia ya fue procesada.")
            return
        row = await (await db.execute("SELECT coins FROM economy WHERE user_id=?", (sender.id,))).fetchone()
        if not row or row[0] < amount:
            await db.rollback()
            await message.reply("❌ No tienes suficientes soles.")
            return
        await db.execute("UPDATE economy SET coins=coins-? WHERE user_id=?", (amount, sender.id))
        await db.execute("UPDATE economy SET coins=coins+? WHERE user_id=?", (amount, target_id))
        await db.commit()
    await message.reply(
        f"🧾 <b>Transferencia completada</b>\n\n💸 Monto: <b>S/ {amount}</b>\n"
        f"👤 Destino: <b>{html.escape(target_name)}</b>\n🆔 <code>{target_id}</code>", parse_mode="HTML"
    )


@router.message(Command("tienda"))
async def shop(message: Message):
    await _init_user(message.from_user.id, message.from_user.full_name, message.chat.id)
    lines = ["🛍 <b>Tienda</b>", ""]
    keyboard = InlineKeyboardBuilder()
    for key, (name, price, description) in SHOP.items():
        lines.append(f"<b>{name}</b> — S/ {price}\n{description}")
        keyboard.button(text=f"Comprar {name} · S/ {price}", callback_data=f"shop:buy:{key}")
    keyboard.button(text="🎒 Ver inventario", callback_data="shop:inventory")
    keyboard.adjust(1)
    await message.reply("\n\n".join(lines), parse_mode="HTML", reply_markup=keyboard.as_markup())


@router.message(Command("comprar"))
async def buy(message: Message, command: CommandObject):
    key = (command.args or "").strip().lower()
    if key not in SHOP:
        await message.reply("Objeto inválido. Consulta /tienda.")
        return
    result = await _buy_item(message.from_user.id, message.from_user.full_name, message.chat.id, key)
    await message.reply(result, parse_mode="HTML")


async def _buy_item(user_id: int, full_name: str, chat_id: int, key: str) -> str:
    await _init_user(user_id, full_name, chat_id)
    name, price, _ = SHOP[key]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        owned = await (await db.execute("SELECT quantity FROM inventory WHERE user_id=? AND item_key=?", (user_id, key))).fetchone()
        if owned and owned[0] > 0:
            await db.rollback()
            return f"🎒 Ya tienes {name}. Su efecto se aplica automáticamente; no necesitas comprarlo otra vez."
        balance = await (await db.execute("SELECT coins FROM economy WHERE user_id=?", (user_id,))).fetchone()
        if not balance or balance[0] < price:
            await db.rollback()
            return f"❌ Necesitas S/ {price} para comprar {name}."
        await db.execute("UPDATE economy SET coins=coins-? WHERE user_id=?", (price, user_id))
        await db.execute("""INSERT INTO inventory(user_id,item_key,quantity) VALUES(?,?,1)
            ON CONFLICT(user_id,item_key) DO UPDATE SET quantity=quantity+1""", (user_id, key))
        await db.commit()
    return f"✅ Compraste <b>{name}</b> por <b>S/ {price}</b>. Ya aparece en /inventario."


@router.callback_query(F.data.startswith("shop:buy:"))
async def buy_callback(callback: CallbackQuery):
    key = callback.data.rsplit(":", 1)[1]
    if key not in SHOP:
        await callback.answer("Objeto inválido.", show_alert=True)
        return
    result = await _buy_item(callback.from_user.id, callback.from_user.full_name, callback.message.chat.id, key)
    await callback.answer(result.replace("<b>", "").replace("</b>", ""), show_alert=True)


@router.message(Command("inventario", "inv"))
async def inventory(message: Message):
    user = message.from_user
    await _init_user(user.id, user.full_name, message.chat.id)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT item_key,quantity FROM inventory WHERE user_id=? AND quantity>0", (user.id,)
        )).fetchall()
    if not rows:
        await message.reply("🎒 Tu inventario está vacío. Mira /tienda.")
        return
    lines = [f"{SHOP[key][0]} × {quantity}\n{SHOP[key][2]}" for key, quantity in rows if key in SHOP]
    kb = InlineKeyboardBuilder()
    for key, quantity in rows:
        if key in SHOP:
            kb.button(text=f"ℹ️ {SHOP[key][0]}", callback_data=f"inventory:info:{user.id}:{key}")
    kb.adjust(1)
    await message.reply("🎒 <b>Tu inventario</b>\n\nLos beneficios se aplican automáticamente; los coleccionables son decorativos.\n\n" + "\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "shop:inventory")
async def inventory_callback(callback: CallbackQuery):
    await _init_user(callback.from_user.id, callback.from_user.full_name, callback.message.chat.id)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT item_key,quantity FROM inventory WHERE user_id=? AND quantity>0", (callback.from_user.id,)
        )).fetchall()
    lines = [f"{SHOP[key][0]} × {quantity}\n{SHOP[key][2]}" for key, quantity in rows if key in SHOP]
    await callback.message.reply(
        "🎒 <b>Tu inventario</b>\n\n" + ("\n".join(lines) if lines else "Está vacío."),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("inventory:info:"))
async def inventory_info(callback: CallbackQuery):
    _, _, owner, key = callback.data.split(":")
    if str(callback.from_user.id) != owner or key not in SHOP:
        await callback.answer("Abre tu propio /inventario.", show_alert=True)
        return
    quantity = await _item_count(callback.from_user.id, key)
    name, _, description = SHOP[key]
    await callback.answer(f"{name} × {quantity}\n{description}", show_alert=True)


def _calc(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS: return OPS[type(node.op)](_calc(node.left), _calc(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS: return OPS[type(node.op)](_calc(node.operand))
    raise ValueError("expresión no permitida")


@router.message(Command("calcular", "cal"))
async def calculate(message: Message, command: CommandObject):
    if not command.args:
        await message.reply("Usa /calcular 2*(5+3)")
        return
    try:
        status = await _animate(message, [
            f"🧮 Operación: <code>{html.escape(command.args)}</code>",
            "🔢 Ordenando números y operadores…",
            "⚙️ Calculando resultado…",
        ], delay=0.45)
        result = _calc(ast.parse(command.args, mode="eval").body)
        await status.edit_text(
            f"🧮 <b>Calculadora</b>\n\n<code>{html.escape(command.args)}</code>\n➗ Resultado: <b>{result}</b>",
            parse_mode="HTML",
        )
    except Exception:
        await message.reply("❌ Expresión inválida. Usa números y operadores + - * / % **.")
