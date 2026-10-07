async def render_group_template(bot, chat, user, template: str) -> str:
    username = f"@{user.username}" if user.username else "sin usuario"
    try:
        members = await bot.get_chat_member_count(chat.id)
    except Exception:
        members = "?"
    values = {
        "{name}": user.full_name,
        "{username}": username,
        "{group}": chat.title or "este grupo",
        "{members}": str(members),
        "{id}": str(user.id),
    }
    result = template
    for variable, value in values.items():
        result = result.replace(variable, value)
    return result
