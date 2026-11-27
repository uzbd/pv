from __future__ import annotations

import csv
import hmac
import hashlib
import base64
import io
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .config import ConfigError, RUNTIME_SESSION_SECRET, Settings
from .core.parsing import extract_tags_and_links, iso_utc
from .core.telegram_export import parse_saved_messages_export
from .storage_factory import create_storage

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("personal_vault_web")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(BASE_DIR, "static", "ui")
UI_INDEX = os.path.join(UI_DIR, "index.html")
os.makedirs(UI_DIR, exist_ok=True)
TEMPLATES = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
LOGIN_FAILURES: dict[str, list[float]] = {}
LOGIN_LOCK = threading.Lock()
ACTIVE_SESSIONS: dict[str, float] = {}
ACTIVE_SESSIONS_LOCK = threading.Lock()
SETUP_LOCK = threading.Lock()
AUTH_CONFIG_PATH = ".personal-vault-web/auth.json"
PASSWORD_HASH_ITERATIONS = 600_000


class AuthRequired(Exception):
    pass


def _hash_password(password: str) -> dict[str, Any]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
    return {
        "version": 1,
        "scheme": "pbkdf2-sha256",
        "iterations": PASSWORD_HASH_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "digest": base64.b64encode(digest).decode("ascii"),
        "created_at": iso_utc(),
    }


def _verify_password_hash(password: str, config: dict[str, Any]) -> bool:
    try:
        if config.get("scheme") != "pbkdf2-sha256":
            return False
        iterations = int(config.get("iterations", 0))
        if iterations < 200_000 or iterations > 2_000_000:
            return False
        salt = base64.b64decode(str(config["salt"]), validate=True)
        expected = base64.b64decode(str(config["digest"]), validate=True)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (KeyError, TypeError, ValueError):
        return False


def _load_auth_config(vault: Any) -> dict[str, Any] | None:
    github = getattr(vault, "github", None)
    if not github:
        return None
    raw = github.get_text(AUTH_CONFIG_PATH)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The saved website access settings in GitHub are invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("scheme") != "pbkdf2-sha256":
        raise RuntimeError("The saved website access settings in GitHub are invalid")
    return payload


def _save_auth_config(request: Request, password: str) -> dict[str, Any]:
    vault = _get_storage(request)
    if not getattr(vault, "github", None):
        raise HTTPException(status_code=400, detail="Password setup requires GitHub storage")
    config = _hash_password(password)
    try:
        vault.github.put_file(
            AUTH_CONFIG_PATH,
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            "Update Personal Vault website access settings",
        )
    except Exception as exc:
        log.error("Could not save website access settings (%s)", exc.__class__.__name__)
        raise HTTPException(
            status_code=502,
            detail="Could not save the password verifier to your private GitHub repository. Check PAT Contents read/write access.",
        ) from exc
    request.app.state.auth_config = config
    request.app.state.setup_required = False
    return config


def _password_matches(request: Request, candidate: str) -> bool:
    if len(candidate) > 1024:
        return False
    auth_config = getattr(request.app.state, "auth_config", None)
    if auth_config:
        return _verify_password_hash(candidate, auth_config)
    settings: Settings = request.app.state.settings
    if settings.app_password:
        return hmac.compare_digest(candidate.encode("utf-8"), settings.app_password.encode("utf-8"))
    return False


def _establish_session(request: Request) -> str:
    _revoke_session(request)
    session_id = secrets.token_urlsafe(32)
    max_age = int(request.app.state.settings.session_max_age)
    now = time.time()
    with ACTIVE_SESSIONS_LOCK:
        # Opportunistically remove expired sessions and keep the allowlist bounded.
        expired = [key for key, expires in ACTIVE_SESSIONS.items() if expires <= now]
        for key in expired:
            ACTIVE_SESSIONS.pop(key, None)
        ACTIVE_SESSIONS[session_id] = now + max_age
    request.session["authenticated"] = True
    request.session["session_id"] = session_id
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    request.session["login_at"] = iso_utc()
    return request.session["csrf_token"]


def _revoke_session(request: Request) -> None:
    session_id = request.session.get("session_id")
    if session_id:
        with ACTIVE_SESSIONS_LOCK:
            ACTIVE_SESSIONS.pop(str(session_id), None)
    request.session.clear()


def _revoke_all_sessions() -> None:
    with ACTIVE_SESSIONS_LOCK:
        ACTIVE_SESSIONS.clear()


def _session_is_active(request: Request) -> bool:
    if not request.session.get("authenticated"):
        return False
    session_id = str(request.session.get("session_id", ""))
    if not session_id:
        return False
    now = time.time()
    with ACTIVE_SESSIONS_LOCK:
        expires = ACTIVE_SESSIONS.get(session_id)
        if expires is None:
            return False
        if expires <= now:
            ACTIVE_SESSIONS.pop(session_id, None)
            return False
        return True


def _ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def _verify_csrf(request: Request, token: str) -> None:
    expected = str(request.session.get("csrf_token", ""))
    if not expected or not hmac.compare_digest(expected, token or ""):
        raise HTTPException(status_code=403, detail="The form expired. Reload the page and try again.")


def _flash(request: Request, message: str, kind: str = "success") -> None:
    request.session["flash"] = {"message": message, "kind": kind}


def _render(request: Request, template: str, **context: Any) -> HTMLResponse:
    flash = request.session.pop("flash", None)
    settings: Settings = request.app.state.settings
    merged = {
        "request": request,
        "csrf_token": _ensure_csrf(request),
        "flash": flash,
        "app_title": settings.app_title,
        "active_path": request.url.path,
        "settings": settings,
        **context,
    }
    return TEMPLATES.TemplateResponse(request=request, name=template, context=merged)


def _get_storage(request: Request):
    storage = getattr(request.app.state, "vault", None)
    if storage is None:
        raise HTTPException(status_code=503, detail="Vault storage is not ready")
    return storage


def _require_auth(request: Request) -> None:
    if not _session_is_active(request):
        raise AuthRequired()


def _rate_limit_key(request: Request) -> str:
    # Do not trust arbitrary X-Forwarded-For headers. A reverse proxy can be
    # configured separately if the deployment provides a trusted proxy layer.
    return request.client.host if request.client else "unknown"


def _login_limited(key: str) -> bool:
    now = time.time()
    with LOGIN_LOCK:
        attempts = [stamp for stamp in LOGIN_FAILURES.get(key, []) if now - stamp < 900]
        LOGIN_FAILURES[key] = attempts
        return len(attempts) >= 5


def _record_login_failure(key: str) -> None:
    now = time.time()
    with LOGIN_LOCK:
        attempts = [stamp for stamp in LOGIN_FAILURES.get(key, []) if now - stamp < 900]
        attempts.append(now)
        LOGIN_FAILURES[key] = attempts


def _clear_login_failures(key: str) -> None:
    with LOGIN_LOCK:
        LOGIN_FAILURES.pop(key, None)


def _normalise_import_records(records: list[Any]) -> tuple[list[dict[str, Any]], int]:
    normalized: list[dict[str, Any]] = []
    skipped = 0
    for item in records:
        if not isinstance(item, dict):
            skipped += 1
            continue
        record_id = str(item.get("id", "")).strip()
        text = item.get("text")
        if (
            not record_id
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", record_id)
            or not isinstance(text, str)
            or not text.strip()
        ):
            skipped += 1
            continue
        record = dict(item)
        record["id"] = record_id
        record["text"] = text
        record.setdefault("created_at", iso_utc())
        record.setdefault("updated_at", record.get("edited_at") or record["created_at"])
        record.setdefault("edited_at", None)
        entities = record.get("entities") if isinstance(record.get("entities"), list) else []
        record["entities"] = entities
        tags, links = extract_tags_and_links(text, entities)
        raw_tags = record.get("hashtags")
        raw_links = record.get("links")
        record["hashtags"] = sorted({str(tag).casefold().lstrip("#") for tag in (raw_tags or [])} | set(tags)) if isinstance(raw_tags, list) else tags
        record["links"] = sorted({str(link) for link in (raw_links or [])} | set(links)) if isinstance(raw_links, list) else links
        record.setdefault("is_deleted", False)
        record.setdefault("deleted_at", None)
        record.setdefault("schema_version", 1)
        normalized.append(record)
    return normalized, skipped


def _parse_upload(filename: str, raw: bytes) -> tuple[list[dict[str, Any]], int, str]:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "jsonl":
        imported: list[Any] = []
        ignored = 0
        for line in raw.decode("utf-8-sig").splitlines():
            if not line.strip():
                continue
            try:
                imported.append(json.loads(line))
            except json.JSONDecodeError:
                ignored += 1
        records, invalid = _normalise_import_records(imported)
        return records, ignored + invalid, "Vault JSONL"
    if suffix != "json":
        raise ValueError("শুধু Telegram Desktop-এর .json অথবা Vault-এর .jsonl ফাইল গ্রহণ করা হয়।")

    payload = json.loads(raw.decode("utf-8-sig"))
    if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
        records, ignored = parse_saved_messages_export(payload)
        records, invalid = _normalise_import_records(records)
        return records, ignored + invalid, "Telegram Saved Messages JSON"

    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        source_records = payload["records"]
        source_name = "Vault JSON"
    elif isinstance(payload, list):
        source_records = payload
        source_name = "JSON records"
    else:
        raise ValueError("JSON ফাইলে Telegram messages অথবা records array পাওয়া যায়নি।")
    records, ignored = _normalise_import_records(source_records)
    return records, ignored, source_name


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    logging.getLogger().setLevel(settings.log_level)
    log.info("Starting %s with storage mode %s", settings.app_title, settings.storage_mode)
    vault = create_storage(settings)
    app.state.settings = settings
    app.state.vault = vault
    app.state.auth_config = _load_auth_config(vault)
    app.state.setup_required = not bool(app.state.auth_config or settings.app_password)
    app.state.setup_lock = SETUP_LOCK
    yield
    log.info("%s is shutting down", settings.app_title)


app = FastAPI(title="Personal Vault", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=RUNTIME_SESSION_SECRET,
    session_cookie="personal_vault_session",
    max_age=max(600, min(int(os.getenv("SESSION_MAX_AGE", "86400")) if os.getenv("SESSION_MAX_AGE", "86400").isdigit() else 86400, 2592000)),
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE", "true").casefold() not in {"0", "false", "no", "off"},
)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/static/ui", StaticFiles(directory=UI_DIR, check_dir=False), name="ui-static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "font-src 'self' data:; img-src 'self' data:; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
    )
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path != "/health" and not request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(AuthRequired)
async def auth_required_handler(request: Request, exc: AuthRequired):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/health", include_in_schema=False)
@app.get("/healthz", include_in_schema=False)
async def health(request: Request):
    ready = getattr(request.app.state, "vault", None) is not None
    return {"status": "ok" if ready else "starting", "service": "personal-vault-web"}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if os.path.isfile(UI_INDEX):
        return FileResponse(UI_INDEX)
    if request.session.get("authenticated"):
        return RedirectResponse("/", status_code=303)
    if not request.session.get("csrf_token"):
        _ensure_csrf(request)
    return _render(request, "login.html")


@app.post("/login")
async def login(
    request: Request,
    password: str = Form(...),
    csrf_token: str = Form(...),
):
    _verify_csrf(request, csrf_token)
    key = _rate_limit_key(request)
    if _login_limited(key):
        _flash(request, "Too many login attempts. Try again in 15 minutes.", "error")
        return RedirectResponse("/login", status_code=303)
    if not _password_matches(request, password):
        _record_login_failure(key)
        _flash(request, "পাসওয়ার্ড সঠিক নয়।", "error")
        return RedirectResponse("/login", status_code=303)
    _clear_login_failures(key)
    _establish_session(request)
    _flash(request, "সুরক্ষিত Vault-এ স্বাগতম।")
    return RedirectResponse("/", status_code=303)


protected = APIRouter(dependencies=[Depends(_require_auth)])


@protected.post("/logout")
async def logout(request: Request, csrf_token: str = Form(...)):
    _verify_csrf(request, csrf_token)
    _revoke_session(request)
    return RedirectResponse("/login", status_code=303)


@protected.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if os.path.isfile(UI_INDEX):
        return FileResponse(UI_INDEX)
    storage = _get_storage(request)
    stats = storage.stats()
    recent = storage.recent(8)
    return _render(request, "dashboard.html", stats=stats, recent=recent)


@protected.get("/app", response_class=HTMLResponse)
@protected.get("/app/{spa_path:path}", response_class=HTMLResponse)
async def spa_routes(request: Request, spa_path: str = ""):
    if os.path.isfile(UI_INDEX):
        return FileResponse(UI_INDEX)
    return RedirectResponse("/", status_code=303)


@protected.get("/messages", response_class=HTMLResponse)
async def messages_page(
    request: Request,
    q: str = "",
    tag: str = "",
    domain: str = "",
    date: str = "",
    from_date: str = "",
    to_date: str = "",
    show_deleted: bool = False,
    page: int = 1,
):
    storage = _get_storage(request)
    records = storage.all_records(include_deleted=True)
    qn = q.casefold().strip()
    tag_n = tag.casefold().strip().lstrip("#")
    domain_n = domain.casefold().strip()
    filtered: list[dict[str, Any]] = []
    for record in records:
        if record.get("is_deleted") and not show_deleted:
            continue
        text = str(record.get("text", ""))
        tags = [str(value).casefold().lstrip("#") for value in record.get("hashtags", [])]
        links = [str(value).casefold() for value in record.get("links", [])]
        created_date = str(record.get("created_at", ""))[:10]
        if qn and qn not in text.casefold() and qn not in " ".join(tags) and qn not in " ".join(links):
            continue
        if tag_n and tag_n not in tags:
            continue
        if domain_n and not any(domain_n in link for link in links):
            continue
        if date and created_date != date:
            continue
        if from_date and created_date < from_date:
            continue
        if to_date and created_date > to_date:
            continue
        filtered.append(record)

    per_page = 20
    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    current_page = max(1, min(page, total_pages))
    start = (current_page - 1) * per_page
    page_records = filtered[start : start + per_page]
    query_values = {
        "q": q, "tag": tag, "domain": domain, "date": date,
        "from_date": from_date, "to_date": to_date,
        "show_deleted": show_deleted,
    }
    return _render(
        request,
        "messages.html",
        records=page_records,
        total=total,
        page=current_page,
        total_pages=total_pages,
        query_values=query_values,
    )


@protected.get("/messages/new", response_class=HTMLResponse)
async def new_message_page(request: Request):
    return _render(request, "message_form.html", record=None, form_title="নতুন নোট")


@protected.post("/messages/new")
async def create_message(request: Request, text: str = Form(...), csrf_token: str = Form(...)):
    _verify_csrf(request, csrf_token)
    text = text.strip()
    if not text:
        _flash(request, "খালি মেসেজ সংরক্ষণ করা যায় না।", "error")
        return RedirectResponse("/messages/new", status_code=303)
    now = iso_utc()
    tags, links = extract_tags_and_links(text, [])
    record = {
        "id": "web_" + uuid.uuid4().hex,
        "created_at": now,
        "updated_at": now,
        "edited_at": None,
        "text": text,
        "entities": [],
        "hashtags": tags,
        "links": links,
        "is_deleted": False,
        "deleted_at": None,
        "schema_version": 1,
        "source": "web",
    }
    _get_storage(request).add_or_update(record)
    _flash(request, "নতুন নোট Vault-এ সংরক্ষিত হয়েছে।")
    return RedirectResponse("/messages", status_code=303)


@protected.get("/messages/{record_id}", response_class=HTMLResponse)
async def message_detail(request: Request, record_id: str):
    record = _get_storage(request).get(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Message not found")
    return _render(request, "message_detail.html", record=record)


@protected.get("/messages/{record_id}/edit", response_class=HTMLResponse)
async def edit_message_page(request: Request, record_id: str):
    record = _get_storage(request).get(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Message not found")
    return _render(request, "message_form.html", record=record, form_title="মেসেজ সম্পাদনা")


@protected.post("/messages/{record_id}/edit")
async def edit_message(request: Request, record_id: str, text: str = Form(...), csrf_token: str = Form(...)):
    _verify_csrf(request, csrf_token)
    updated = _get_storage(request).update_text(record_id, text.strip(), [])
    if not updated:
        raise HTTPException(status_code=404, detail="Message not found")
    _flash(request, "মেসেজটি আপডেট করা হয়েছে।")
    return RedirectResponse(f"/messages/{record_id}", status_code=303)


@protected.post("/messages/{record_id}/delete")
async def delete_message(request: Request, record_id: str, csrf_token: str = Form(...)):
    _verify_csrf(request, csrf_token)
    success = _get_storage(request).set_deleted(record_id, True)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    _flash(request, "মেসেজটি Trash-এ সরানো হয়েছে।")
    return RedirectResponse("/messages?show_deleted=true", status_code=303)


@protected.post("/messages/{record_id}/restore")
async def restore_message(request: Request, record_id: str, csrf_token: str = Form(...)):
    _verify_csrf(request, csrf_token)
    success = _get_storage(request).set_deleted(record_id, False)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    _flash(request, "মেসেজটি Restore করা হয়েছে।")
    return RedirectResponse(f"/messages/{record_id}", status_code=303)


@protected.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    stats = _get_storage(request).stats()
    config: Settings = request.app.state.settings
    return _render(request, "settings.html", stats=stats, config=config)


@protected.post("/settings/backup")
async def backup_now(request: Request, csrf_token: str = Form(...)):
    _verify_csrf(request, csrf_token)
    storage = _get_storage(request)
    if not storage.drive:
        _flash(request, "Google Drive কনফিগার করা নেই।", "warning")
    elif not storage.github:
        _flash(request, "Google Drive-ই Primary Storage; আলাদা secondary backup প্রয়োজন নেই।", "info")
    else:
        success, failed = storage.backup_now()
        kind = "success" if failed == 0 else "warning"
        _flash(request, f"Drive Backup সম্পন্ন। সফল: {success}, Pending/ব্যর্থ: {failed}", kind)
    return RedirectResponse("/settings#backup", status_code=303)


@protected.post("/settings/import")
async def import_file(
    request: Request,
    csrf_token: str = Form(...),
    file: UploadFile = File(...),
):
    _verify_csrf(request, csrf_token)
    config: Settings = request.app.state.settings
    filename = file.filename or "upload"
    raw = await file.read(config.max_upload_mb * 1024 * 1024 + 1)
    if len(raw) > config.max_upload_mb * 1024 * 1024:
        _flash(request, f"ফাইলটি {config.max_upload_mb} MB সীমা অতিক্রম করেছে।", "error")
        return RedirectResponse("/settings#import", status_code=303)
    try:
        records, ignored, source_name = _parse_upload(filename, raw)
        if not records:
            _flash(request, f"কোনো গ্রহণযোগ্য text record পাওয়া যায়নি। বাদ পড়েছে: {ignored}", "warning")
            return RedirectResponse("/settings#import", status_code=303)
        added, updated, skipped = _get_storage(request).import_records(records)
        storage_name = _get_storage(request).stats()["primary_storage"]
        _flash(
            request,
            f"{source_name} Import সম্পন্ন — নতুন: {added}, Edit আপডেট: {updated}, Duplicate/পুরোনো বাদ: {skipped}, Invalid/media/খালি বাদ: {ignored}. পুরোনো অন্য মেসেজ অক্ষত আছে। সংরক্ষণ: {storage_name}.",
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _flash(request, f"Import করা যায়নি: {exc}", "error")
    except Exception as exc:
        log.error("Vault import failed (%s)", exc.__class__.__name__)
        _flash(request, "Import ব্যর্থ হয়েছে। Storage credentials ও network পরীক্ষা করো।", "error")
    return RedirectResponse("/settings#import", status_code=303)


@protected.get("/settings/export.jsonl")
async def export_jsonl(request: Request):
    content = _get_storage(request).export_jsonl().encode("utf-8")
    headers = {"Content-Disposition": 'attachment; filename="personal-vault-export.jsonl"'}
    return Response(content, media_type="application/x-ndjson; charset=utf-8", headers=headers)


@protected.get("/settings/export.json")
async def export_json(request: Request):
    records = _get_storage(request).all_records(include_deleted=True)
    payload = {
        "format": "personal-vault-json-export",
        "schema_version": 1,
        "exported_at": iso_utc(),
        "records": records,
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    headers = {"Content-Disposition": 'attachment; filename="personal-vault-export.json"'}
    return Response(content, media_type="application/json; charset=utf-8", headers=headers)


@protected.get("/settings/export.csv")
async def export_csv(request: Request):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=["id", "created_at", "updated_at", "edited_at", "text", "hashtags", "links", "is_deleted"],
    )
    writer.writeheader()
    for record in _get_storage(request).all_records(include_deleted=True):
        writer.writerow({
            "id": record.get("id", ""),
            "created_at": record.get("created_at", ""),
            "updated_at": record.get("updated_at", ""),
            "edited_at": record.get("edited_at", ""),
            "text": record.get("text", ""),
            "hashtags": " ".join(record.get("hashtags", [])),
            "links": " ".join(record.get("links", [])),
            "is_deleted": bool(record.get("is_deleted", False)),
        })
    content = buffer.getvalue().encode("utf-8-sig")
    headers = {"Content-Disposition": 'attachment; filename="personal-vault-export.csv"'}
    return Response(content, media_type="text/csv; charset=utf-8", headers=headers)


# JSON API used by the React application. It reuses the exact Vault storage
# engine and signed-session security model used by the legacy HTML interface.
def _require_api_auth(request: Request) -> None:
    if not _session_is_active(request):
        raise HTTPException(status_code=401, detail="Authentication required")


def _api_csrf(request: Request, fallback: str = "") -> None:
    token = request.headers.get("X-CSRF-Token", "") or fallback
    _verify_csrf(request, token)


api_public = APIRouter(prefix="/api")
api_private = APIRouter(prefix="/api", dependencies=[Depends(_require_api_auth)])


@api_public.get("/auth/session")
async def api_session(request: Request):
    return {
        "authenticated": _session_is_active(request),
        "setup_required": bool(getattr(request.app.state, "setup_required", False)),
        "csrf_token": _ensure_csrf(request),
    }


@api_public.post("/auth/setup")
async def api_setup(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    _api_csrf(request)
    if not request.app.state.setup_required:
        raise HTTPException(status_code=409, detail="Initial setup has already been completed")
    key = _rate_limit_key(request)
    if _login_limited(key):
        raise HTTPException(status_code=429, detail="Too many setup attempts. Try again in 15 minutes.")
    password = str(payload.get("password", "")) if isinstance(payload, dict) else ""
    confirm = str(payload.get("confirm_password", "")) if isinstance(payload, dict) else ""
    setup_key = str(payload.get("setup_key", "")) if isinstance(payload, dict) else ""
    settings: Settings = request.app.state.settings
    # The website never asks the browser to collect a GitHub PAT. A separate
    # one-time setup key proves deployment ownership without exposing storage
    # credentials to the page or its network requests.
    if not settings.setup_key:
        raise HTTPException(status_code=503, detail="Initial setup is locked. Configure VAULT_SETUP_KEY in your hosting environment.")
    if not hmac.compare_digest(setup_key.encode("utf-8"), settings.setup_key.encode("utf-8")):
        _record_login_failure(key)
        raise HTTPException(status_code=401, detail="The one-time setup key is incorrect.")
    if len(password) < 16 or len(password) > 1024:
        raise HTTPException(status_code=422, detail="Choose a strong password between 16 and 1024 characters.")
    if password != confirm:
        raise HTTPException(status_code=422, detail="The passwords do not match.")
    # Serialize setup attempts so two first-run requests cannot race to claim the vault.
    with SETUP_LOCK:
        if not request.app.state.setup_required:
            raise HTTPException(status_code=409, detail="Initial setup has already been completed")
        _save_auth_config(request, password)
    _clear_login_failures(key)
    csrf = _establish_session(request)
    return {"ok": True, "csrf_token": csrf}


@api_public.post("/auth/login")
async def api_login(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    password = str(payload.get("password", "")) if isinstance(payload, dict) else ""
    csrf_fallback = str(payload.get("csrf_token", "")) if isinstance(payload, dict) else ""
    _api_csrf(request, csrf_fallback)
    if request.app.state.setup_required:
        raise HTTPException(status_code=409, detail="Complete the initial workspace setup first")
    key = _rate_limit_key(request)
    if _login_limited(key):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again in 15 minutes.")
    if not _password_matches(request, password):
        _record_login_failure(key)
        raise HTTPException(status_code=401, detail="পাসওয়ার্ড সঠিক নয়।")
    _clear_login_failures(key)
    csrf = _establish_session(request)
    return {"ok": True, "csrf_token": csrf}


@api_private.post("/auth/logout")
async def api_logout(request: Request):
    _api_csrf(request)
    _revoke_session(request)
    return {"ok": True}


@api_private.post("/auth/password")
async def api_change_password(request: Request):
    _api_csrf(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    current = str(payload.get("current_password", "")) if isinstance(payload, dict) else ""
    new_password = str(payload.get("new_password", "")) if isinstance(payload, dict) else ""
    confirm = str(payload.get("confirm_password", "")) if isinstance(payload, dict) else ""
    if not _password_matches(request, current):
        raise HTTPException(status_code=401, detail="Your current password is incorrect.")
    if len(new_password) < 16 or len(new_password) > 1024:
        raise HTTPException(status_code=422, detail="Choose a strong password between 16 and 1024 characters.")
    if new_password != confirm:
        raise HTTPException(status_code=422, detail="The new passwords do not match.")
    _save_auth_config(request, new_password)
    # Password rotation invalidates every previously issued browser session.
    _revoke_all_sessions()
    csrf = _establish_session(request)
    return {"ok": True, "csrf_token": csrf}


@api_private.get("/dashboard")
async def api_dashboard(request: Request):
    storage = _get_storage(request)
    records = storage.all_records(include_deleted=True)
    recent = storage.recent(8)
    tag_counts: dict[str, int] = {}
    for record in records:
        if record.get("is_deleted"):
            continue
        for tag in record.get("hashtags", []):
            key = str(tag).casefold().lstrip("#")
            if key:
                tag_counts[key] = tag_counts.get(key, 0) + 1
    top_tags = [{"tag": tag, "count": count} for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:8]]
    return {"stats": storage.stats(), "recent": recent, "top_tags": top_tags}


@api_private.get("/messages")
async def api_messages(
    request: Request, q: str = "", tag: str = "", domain: str = "",
    date: str = "", from_date: str = "", to_date: str = "", kind: str = "",
    include_deleted: bool = False, only_deleted: bool = False, page: int = 1, per_page: int = 24,
):
    kind = kind.casefold().strip()
    if kind not in ("", "links"):
        raise HTTPException(status_code=422, detail="This content category is not supported by the current text-only vault")
    storage = _get_storage(request)
    qn, tag_n, domain_n = q.casefold().strip(), tag.casefold().strip().lstrip("#"), domain.casefold().strip()
    filtered: list[dict[str, Any]] = []
    for record in storage.all_records(include_deleted=True):
        if record.get("is_deleted") and not (include_deleted or only_deleted):
            continue
        if only_deleted and not record.get("is_deleted"):
            continue
        text = str(record.get("text", ""))
        tags = [str(value).casefold().lstrip("#") for value in record.get("hashtags", [])]
        links = [str(value).casefold() for value in record.get("links", [])]
        created_date = str(record.get("created_at", ""))[:10]
        if qn and qn not in text.casefold() and qn not in " ".join(tags) and qn not in " ".join(links):
            continue
        if tag_n and tag_n not in tags:
            continue
        if domain_n and not any(domain_n in link for link in links):
            continue
        if kind == "links" and not links:
            continue
        if date and created_date != date:
            continue
        if from_date and created_date < from_date:
            continue
        if to_date and created_date > to_date:
            continue
        filtered.append(record)
    per_page = max(5, min(per_page, 100))
    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    current_page = max(1, min(page, total_pages))
    start = (current_page - 1) * per_page
    return {"records": filtered[start:start + per_page], "total": total, "page": current_page, "per_page": per_page, "total_pages": total_pages}


@api_private.post("/messages")
async def api_create_message(request: Request):
    _api_csrf(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    text = str(payload.get("text", "")).strip() if isinstance(payload, dict) else ""
    if not text:
        raise HTTPException(status_code=422, detail="খালি নোট সংরক্ষণ করা যায় না।")
    now = iso_utc()
    tags, links = extract_tags_and_links(text, [])
    record = {"id": "web_" + uuid.uuid4().hex, "created_at": now, "updated_at": now, "edited_at": None, "text": text, "entities": [], "hashtags": tags, "links": links, "is_deleted": False, "deleted_at": None, "schema_version": 1, "source": "web"}
    _get_storage(request).add_or_update(record)
    return {"ok": True, "record": record}


@api_private.get("/messages/{record_id}")
async def api_get_message(request: Request, record_id: str):
    record = _get_storage(request).get(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"record": record}


@api_private.patch("/messages/{record_id}")
async def api_edit_message(request: Request, record_id: str):
    _api_csrf(request)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    text = str(payload.get("text", "")).strip() if isinstance(payload, dict) else ""
    if not text:
        raise HTTPException(status_code=422, detail="খালি মেসেজ সংরক্ষণ করা যায় না।")
    if not _get_storage(request).update_text(record_id, text, []):
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True, "record": _get_storage(request).get(record_id)}


@api_private.delete("/messages/{record_id}")
async def api_delete_message(request: Request, record_id: str):
    _api_csrf(request)
    if not _get_storage(request).set_deleted(record_id, True):
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}


@api_private.post("/messages/{record_id}/restore")
async def api_restore_message(request: Request, record_id: str):
    _api_csrf(request)
    if not _get_storage(request).set_deleted(record_id, False):
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True}


@api_private.get("/settings")
async def api_settings(request: Request):
    config: Settings = request.app.state.settings
    stats = _get_storage(request).stats()
    return {
        "app_title": config.app_title, "storage_mode": config.storage_mode,
        "github_enabled": config.github_enabled, "drive_enabled": config.drive_enabled,
        "primary_storage": stats.get("primary_storage"), "data_dir": config.data_dir,
        "drive_pending": stats.get("drive_pending", 0),
        "max_records_per_shard": config.max_records_per_shard, "max_upload_mb": config.max_upload_mb,
        "session_max_age": config.session_max_age, "cookie_secure": config.cookie_secure,
        "app_env": os.getenv("APP_ENV", "production"), "stats": stats,
        "password_managed_by": "GitHub private repository" if getattr(request.app.state, "auth_config", None) else ("Hosting environment" if config.app_password else "Initial setup required"),
    }


@api_private.post("/settings/backup")
async def api_backup_now(request: Request):
    _api_csrf(request)
    storage = _get_storage(request)
    if not storage.drive:
        raise HTTPException(status_code=400, detail="Google Drive is not configured")
    if not storage.github:
        return {"ok": True, "message": "Google Drive is the primary storage; no mirror backup is needed.", "success": 0, "failed": 0}
    success, failed = storage.backup_now()
    return {"ok": failed == 0, "message": "Backup retry finished", "success": success, "failed": failed}


@api_private.post("/settings/import")
async def api_import_file(request: Request, file: UploadFile = File(...)):
    _api_csrf(request)
    config: Settings = request.app.state.settings
    filename = file.filename or "upload"
    raw = await file.read(config.max_upload_mb * 1024 * 1024 + 1)
    if len(raw) > config.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"ফাইলটি {config.max_upload_mb} MB সীমা অতিক্রম করেছে।")
    try:
        records, ignored, source_name = _parse_upload(filename, raw)
        if not records:
            return {"ok": True, "source": source_name, "added": 0, "updated": 0, "skipped": 0, "ignored": ignored}
        added, updated, skipped = _get_storage(request).import_records(records)
        return {"ok": True, "source": source_name, "added": added, "updated": updated, "skipped": skipped, "ignored": ignored, "storage": _get_storage(request).stats().get("primary_storage")}
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Import করা যায়নি: {exc}")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Vault import failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=502, detail="Import failed. Check storage credentials and network.")


@api_private.get("/settings/export.{export_format}")
async def api_export(request: Request, export_format: str):
    storage = _get_storage(request)
    records = storage.all_records(include_deleted=True)
    if export_format == "jsonl":
        return Response(storage.export_jsonl().encode("utf-8"), media_type="application/x-ndjson; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="personal-vault-export.jsonl"'})
    if export_format == "json":
        payload = {"format": "personal-vault-json-export", "schema_version": 1, "exported_at": iso_utc(), "records": records}
        return Response(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), media_type="application/json; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="personal-vault-export.json"'})
    if export_format == "csv":
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=["id", "created_at", "updated_at", "edited_at", "text", "hashtags", "links", "is_deleted"])
        writer.writeheader()
        for record in records:
            writer.writerow({"id": record.get("id", ""), "created_at": record.get("created_at", ""), "updated_at": record.get("updated_at", ""), "edited_at": record.get("edited_at", ""), "text": record.get("text", ""), "hashtags": " ".join(record.get("hashtags", [])), "links": " ".join(record.get("links", [])), "is_deleted": bool(record.get("is_deleted", False))})
        return Response(buffer.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="personal-vault-export.csv"'})
    raise HTTPException(status_code=404, detail="Unsupported export format")


app.include_router(api_public)
app.include_router(api_private)


app.include_router(protected)


def run() -> None:
    import uvicorn
    settings = Settings.from_env()
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower(), workers=1)


if __name__ == "__main__":
    run()
