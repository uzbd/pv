from __future__ import annotations

import re
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


HASHTAG_RE = re.compile(r"(?<![\w])#([\w\u0080-\uffff]+)", re.UNICODE)
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\]\[{}\"']+")
TRAILING_URL_PUNCTUATION = ".,!?;:)]}>'\""


def iso_utc(value: datetime | None = None) -> str:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def stable_vault_id(chat_id: int, message_id: int) -> str:
    raw = f"{chat_id}:{message_id}".encode("utf-8")
    return "v_" + sha256(raw).hexdigest()[:12]


def extract_tags_and_links(text: str, entities: list[dict[str, Any]] | None = None) -> tuple[list[str], list[str]]:
    tags = {match.group(1).casefold() for match in HASHTAG_RE.finditer(text or "")}
    links = set()
    for match in URL_RE.finditer(text or ""):
        links.add(match.group(0).rstrip(TRAILING_URL_PUNCTUATION))
    for entity in entities or []:
        if entity.get("type") == "text_link" and entity.get("url"):
            links.add(str(entity["url"]))
        elif entity.get("type") == "url":
            # Telegram offsets are UTF-16 code units. The raw text URL regex is
            # more reliable for extraction, so this branch is intentionally a no-op.
            continue
    return sorted(tags), sorted(links)


def entities_to_dicts(entities: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for entity in entities or []:
        item: dict[str, Any] = {
            "type": getattr(entity, "type", ""),
            "offset": getattr(entity, "offset", 0),
            "length": getattr(entity, "length", 0),
        }
        url = getattr(entity, "url", None)
        if url:
            item["url"] = url
        language = getattr(entity, "language", None)
        if language:
            item["language"] = language
        output.append(item)
    return output


def build_record(message: Any, edited: bool = False) -> dict[str, Any]:
    text = message.text or ""
    entities = entities_to_dicts(message.entities)
    created = iso_utc(message.date)
    edited_at = iso_utc(message.edit_date) if getattr(message, "edit_date", None) else None
    tags, links = extract_tags_and_links(text, entities)
    return {
        "id": stable_vault_id(message.chat.id, message.message_id),
        "telegram_chat_id": int(message.chat.id),
        "telegram_message_id": int(message.message_id),
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
    }


def partition_date(record: dict[str, Any]) -> str:
    value = str(record.get("created_at") or iso_utc())
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y/%m/%d")
