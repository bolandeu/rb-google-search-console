"""Учётные данные Google: ключ сервисного аккаунта (Search Console) и API-ключ PageSpeed.

Всё неинтерактивно: библиотека только читает то, что положили `gsc auth login`
(keychain ОС) или переменные окружения. Порядок поиска ключа сервисного аккаунта:
GSC_GOOGLE_SERVICE_ACCOUNT_JSON → GOOGLE_SERVICE_ACCOUNT_JSON →
GOOGLE_SERVICE_ACCOUNT_FILE (путь к файлу) → keychain `gsc:google`.
Ключа PSI: GSC_PAGESPEED_API_KEY → GOOGLE_PAGESPEED_API_KEY → keychain `gsc:pagespeed`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from ..credentials import manager as credentials
from .errors import InvalidArguments, NotAuthorized
from .version import CLI_NAME

GOOGLE = "google"  # provider в keychain: gsc:google
PAGESPEED = "pagespeed"  # provider в keychain: gsc:pagespeed
SA_FIELD = "service_account_json"

SCOPE_READONLY = "https://www.googleapis.com/auth/webmasters.readonly"
SCOPE_FULL = "https://www.googleapis.com/auth/webmasters"

_LEGACY_SA_JSON_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON"
_LEGACY_SA_FILE_ENV = "GOOGLE_SERVICE_ACCOUNT_FILE"
_LEGACY_PSI_ENV = "GOOGLE_PAGESPEED_API_KEY"

LOGIN_GOOGLE = f"{CLI_NAME} auth login --file <service-account.json>"
LOGIN_PAGESPEED = f"{CLI_NAME} auth login --provider pagespeed"


class AuthStatus(BaseModel):
    """Готовность авторизации — для `spider doctor` и `gsc auth status`.

    google: ok — ключ есть и разбирается; missing — ключа нет; expired — Google
    отверг ключ (отозван/удалён). `expired` бывает только при check=True: без
    сети это не узнать.
    """

    google: Literal["ok", "missing", "expired"]
    pagespeed_key: bool
    account: str | None = None  # email сервисного аккаунта — его добавляют в Search Console
    source: str | None = None  # откуда взят ключ: env / file / keychain
    detail: str | None = None  # почему не ok


def parse_service_account(text: str) -> dict[str, Any]:
    """Разобрать и проверить JSON ключа сервисного аккаунта; ошибка — InvalidArguments."""
    try:
        info = json.loads(text)
    except ValueError as exc:
        raise InvalidArguments(f"Ключ сервисного аккаунта — не JSON: {exc}") from exc
    if not isinstance(info, dict) or info.get("type") != "service_account":
        raise InvalidArguments('Это не ключ сервисного аккаунта: нужен JSON с "type": "service_account".')
    missing = [f for f in ("client_email", "private_key", "token_uri") if not info.get(f)]
    if missing:
        raise InvalidArguments(f"В ключе сервисного аккаунта нет полей: {', '.join(missing)}.")
    return info


def service_account_source() -> tuple[str, str] | None:
    """(JSON ключа, источник) или None, если ключа нигде нет. Не проверяет содержимое."""
    env_value = credentials.read_secret_from_env(GOOGLE, SA_FIELD) or os.environ.get(_LEGACY_SA_JSON_ENV)
    if env_value:
        return env_value, "env"
    path = os.environ.get(_LEGACY_SA_FILE_ENV)
    if path:
        file = Path(path).expanduser()
        if not file.is_file():
            raise NotAuthorized(
                GOOGLE, f"{_LEGACY_SA_FILE_ENV} указывает на несуществующий файл: {file}", action=LOGIN_GOOGLE
            )
        return file.read_text(encoding="utf-8"), "file"
    stored = credentials.get_secret(GOOGLE, SA_FIELD)
    if stored:
        return stored, "keychain"
    return None


def load_service_account() -> dict[str, Any]:
    """Словарь ключа сервисного аккаунта; нет или битый — NotAuthorized с командой-исправлением."""
    found = service_account_source()
    if found is None:
        raise NotAuthorized(GOOGLE, "Нет ключа сервисного аккаунта Google.", action=f"Выполните '{LOGIN_GOOGLE}'.")
    try:
        return parse_service_account(found[0])
    except InvalidArguments as exc:
        raise NotAuthorized(
            GOOGLE, f"Ключ из {found[1]}: {exc.message}", action=f"Выполните '{LOGIN_GOOGLE}'."
        ) from exc


def pagespeed_key() -> str | None:
    return credentials.get_secret(PAGESPEED) or os.environ.get(_LEGACY_PSI_ENV) or None


def google_credentials(*, readonly: bool = True) -> Any:
    """google-auth Credentials сервисного аккаунта (токен ещё не получен — это сделает первый запрос)."""
    from google.oauth2 import service_account

    scopes = [SCOPE_READONLY if readonly else SCOPE_FULL]
    return service_account.Credentials.from_service_account_info(load_service_account(), scopes=scopes)


def refresh_token(creds: Any) -> str:
    """Получить/обновить access token. Отказ Google → NotAuthorized, сеть → ApiError."""
    import google.auth.exceptions
    import google.auth.transport.requests

    from .errors import ApiError

    try:
        creds.refresh(google.auth.transport.requests.Request())
    except google.auth.exceptions.RefreshError as exc:
        raise NotAuthorized(
            GOOGLE,
            f"Google отверг ключ сервисного аккаунта: {exc}",
            action=f"Выполните '{LOGIN_GOOGLE}' с новым ключом.",
        ) from exc
    except google.auth.exceptions.TransportError as exc:
        raise ApiError(GOOGLE, f"не удалось получить токен: {exc}") from exc
    return creds.token


def auth_status(*, check: bool = False) -> AuthStatus:
    """Что есть из авторизации. Без check — без сети; check=True — ещё и получает токен у Google."""
    has_psi = pagespeed_key() is not None
    try:
        found = service_account_source()
        if found is None:
            return AuthStatus(google="missing", pagespeed_key=has_psi, detail=f"выполните '{LOGIN_GOOGLE}'")
        info = parse_service_account(found[0])
    except (NotAuthorized, InvalidArguments) as exc:
        return AuthStatus(google="missing", pagespeed_key=has_psi, detail=exc.message)
    status = AuthStatus(google="ok", pagespeed_key=has_psi, account=info["client_email"], source=found[1])
    if check:
        try:
            refresh_token(google_credentials())
        except NotAuthorized as exc:
            status.google = "expired"
            status.detail = exc.message
    return status
