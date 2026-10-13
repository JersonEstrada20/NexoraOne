"""Structured, backward-compatible timeline helpers for service requests."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_request_event(
    history: str | None,
    text: str,
    *,
    author_type: str = "admin",
    author_id=None,
    kind: str = "note",
    created_at: str | None = None,
) -> str:
    clean_text = str(text or "").strip()
    if not clean_text:
        return (history or "").strip()
    entry = {
        "at": created_at or now_iso(),
        "author_type": author_type,
        "author_id": author_id,
        "kind": kind,
        "text": clean_text,
    }
    serialized = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
    previous = (history or "").strip()
    return f"{previous}\n{serialized}" if previous else serialized


def parse_request_history(
    history: str | None,
    *,
    request_text: str = "",
    request_created_at: str = "",
    user_id=None,
    username: str = "",
    resolved_by=None,
) -> list[dict]:
    """Parse new JSON-line events and old timestamped/plain notes."""
    events = []
    if request_text:
        events.append({
            "at": request_created_at or "",
            "author_type": "user",
            "author_id": user_id,
            "author_label": f"@{username}" if username else f"Usuario {user_id}",
            "kind": "request",
            "text": request_text,
        })
    for line in (history or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except (TypeError, ValueError):
            match = re.match(r"^\[([^\]]+)\]\s*(.*)$", line, re.DOTALL)
            at, text = (match.group(1), match.group(2)) if match else ("", line)
            item = {
                "at": at,
                "author_type": "admin",
                "author_id": resolved_by,
                "kind": "legacy_note",
                "text": text,
            }
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            continue
        author_type = str(item.get("author_type") or "admin")
        author_id = item.get("author_id")
        if author_type == "user":
            label = f"@{username}" if username else f"Usuario {author_id or user_id}"
        elif author_id:
            label = f"Admin {author_id}"
        else:
            label = "Equipo de soporte"
        events.append({
            "at": str(item.get("at") or ""),
            "author_type": author_type,
            "author_id": author_id,
            "author_label": label,
            "kind": str(item.get("kind") or "note"),
            "text": str(item.get("text") or ""),
        })
    return events


def latest_request_message(history: str | None) -> str:
    events = parse_request_history(history)
    return events[-1]["text"] if events else ""
