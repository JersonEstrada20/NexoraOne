"""Small, consistent HTML building blocks for Telegram bot replies."""

from html import escape


def heading(icon: str, label: str) -> str:
    return f"{icon} <b>{escape(str(label))}</b>"


def section(icon: str, label: str) -> str:
    return f"{icon} <b>{escape(str(label))}</b>"


def field(icon: str, label: str, value, *, code: bool = False) -> str:
    rendered = escape(str(value))
    if code:
        rendered = f"<code>{rendered}</code>"
    return f"{icon} <b>{escape(str(label))}:</b> {rendered}"


def notice(icon: str, label: str, detail: str = "") -> str:
    line = heading(icon, label)
    return f"{line}\n{escape(detail)}" if detail else line
