from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .parsing import extract_tags_and_links


def _flatten_text(value: Any) -> tuple[str, list[dict[str, Any]]]:
    if isinstance(value, str):
        return value, []
    if not isinstance(value, list):
        return str(value or ""), []
    pieces: list[str] = []
    entities: list[dict[str, Any]] = []
    offset = 0
    for part in value:
        if isinstance(part, str):
            chunk, kind, href = part, None, None
        elif isinstance(part, dict):
            chunk = str(part.get("text", ""))
            kind, href = part.get("type"), part.get("href")
        else:
            continue
        if not chunk:
            continue
        pieces.append(chunk)
        if kind and kind not in ("plain", "text"):
            entity: dict[str, Any] = {
                "type": "text_link" if kind == "link" and href else str(kind),
                "offset": offset,
                "length": len(chunk.encode("utf-16-le")) // 2,
            }
            if href:
                entity["url"] = str(href)
            entities.append(entity)
        offset += len(chunk.encode("utf-16-le")) // 2
    return "".join(pieces), entities


def _timestamp(value: Any) -> str:
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        try:
            if value.strip().isdigit():
                dt = datetime.fromtimestamp(int(value.strip()), tz=timezone.utc)
            else:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_saved_messages_export(payload: Any) -> tuple[list[dict[str, Any]], int]:
    """Parse Telegram Desktop JSON export for Saved Messages."""
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    chat = payload.get("chat", {}) if isinstance(payload.get("chat"), dict) else {}
    chat_name = str(chat.get("name") or payload.get("name") or "")
    chat_type = str(chat.get("type") or payload.get("type") or "")
    if chat_name and chat_name.casefold() not in ("saved messages", "saved messages (you)"):
        raise ValueError("এই JSON ফাইলটি Saved Messages export বলে মনে হচ্ছে না।")
    if chat_type and chat_type not in ("personal_chat", "saved_messages"):
        raise ValueError("এই JSON ফাইলটি ব্যক্তিগত Saved Messages chat export নয়।")
    chat_id = str(chat.get("id") or payload.get("id") or "saved-messages")
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        raise ValueError("JSON-এ messages array পাওয়া যায়নি।")

    records: list[dict[str, Any]] = []
    skipped = 0
    for item in raw_messages:
        if not isinstance(item, dict) or item.get("type") != "message":
            skipped += 1
            continue
        text, entities = _flatten_text(item.get("text", ""))
        if not text.strip():
            skipped += 1
            continue
        message_id = str(item.get("id", ""))
        if not message_id:
            skipped += 1
            continue
        digest = hashlib.sha256(f"telegram-desktop:{chat_id}:{message_id}".encode()).hexdigest()[:12]
        created = _timestamp(item.get("date_unixtime") or item.get("date"))
        edited_raw = item.get("edited_unixtime") or item.get("edited")
        edited_at = _timestamp(edited_raw) if edited_raw else None
        tags, links = extract_tags_and_links(text, entities)
        records.append({
            "id": f"td_{digest}",
            "telegram_export_chat_id": chat_id,
            "telegram_export_message_id": message_id,
            "created_at": created,
            "updated_at": edited_at or created,
            "edited_at": edited_at,
            "text": text,
            "entities": entities,
            "hashtags": tags,
            "links": links,
            "is_deleted": False,
            "deleted_at": None,
            "schema_version": 1,
            "source": "telegram_desktop_import",
        })
    return records, skipped
