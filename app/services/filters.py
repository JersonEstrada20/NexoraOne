import re
import random
from datetime import datetime, timedelta, timezone
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatPermissions

LINK_REGEX = re.compile(r"(https?://|t\.me/|www\.)", re.IGNORECASE)


def contains_link(text: str) -> bool:
    return bool(LINK_REGEX.search(text or ""))


def contains_bad_word(text: str, words: list[str]):
    text_lower = (text or "").lower()
    for word in words:
        if word in text_lower:
            return word
    return None


def parse_duration_to_minutes(raw: str):
    raw = raw.strip().lower()
    match = re.fullmatch(r"(\d+)([mhd])", raw)
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        return value
    if unit == "h":
        return value * 60
    if unit == "d":
        return value * 1440

    return None


def mute_until(minutes: int):
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def future_iso_minutes(minutes: int):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def is_expired(iso_date: str) -> bool:
    try:
        expires = datetime.fromisoformat(iso_date)
        return datetime.now(timezone.utc) > expires
    except Exception:
        return True


def generate_captcha():
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    answer = a + b

    wrong_1 = answer + random.choice([1, 2, 3])
    wrong_2 = max(1, answer - random.choice([1, 2, 3]))

    options = [str(answer), str(wrong_1), str(wrong_2)]
    random.shuffle(options)

    return f"{a} + {b}", str(answer), options


def parse_int(value: str, minimum: int = 1, maximum: int | None = None):
    try:
        number = int(value.strip())
    except Exception:
        return None

    if number < minimum:
        return None

    if maximum is not None and number > maximum:
        return None

    return number


def full_unrestrict_permissions():
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )


async def is_admin(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        }
    except Exception:
        return False