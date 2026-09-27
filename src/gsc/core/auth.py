"""Учётные данные Google: ключ сервисного аккаунта (Search Console) и API-ключ PageSpeed.

Хранение и поиск — общий пакет google-oauth: один слот keychain на все
Google-инструменты (`google-oauth:service_account`, `google-oauth:api_key/pagespeed`).
Всё неинтерактивно: библиотека только читает то, что положили `gsc auth login`
или переменные окружения. Порядок поиска ключа сервисного аккаунта:
GSC_GOOGLE_SERVICE_ACCOUNT_JSON → GOOGLE_SERVICE_ACCOUNT_JSON → GOOGLE_OAUTH_SERVICE_ACCOUNT_JSON →
GOOGLE_SERVICE_ACCOUNT_FILE / GOOGLE_OAUTH_SERVICE_ACCOUNT_FILE (путь к файлу) → keychain.
Ключа PSI: GSC_PAGESPEED_API_KEY → GOOGLE_PAGESPEED_API_KEY → GOOGLE_OAUTH_PAGESPEED_API_KEY → keychain.
"""

from __future__ import annotations

from typing import Any, Literal

from google_oauth import ApiKey, GoogleAuth, Profile, parse_service_account
from pydantic import BaseModel

from .errors import ApiError, NotAuthorized, TokenRequestFailed
from .version import CLI_NAME

__all__ = ["AuthStatus", "auth_status", "parse_service_account"]

GOOGLE = "google"  # --provider сервисного аккаунта
PAGESPEED = "pagespeed"  # --provider и имя API-ключа PSI

SCOPE_READONLY = "https://www.googleapis.com/auth/webmasters.readonly"
SCOPE_FULL = "https://www.googleapis.com/auth/webmasters"

PROFILE = Profile(
    cli_name=CLI_NAME,
    service="Google Search Console",
    scopes=(SCOPE_READONLY, SCOPE_FULL),
    service_account_env=("GSC_GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SERVICE_ACCOUNT_JSON"),
    service_account_file_env=("GOOGLE_SERVICE_ACCOUNT_FILE",),
    api_keys=(
        ApiKey(
            PAGESPEED,
            "PageSpeed Insights",
            env=("GSC_PAGESPEED_API_KEY", "GOOGLE_PAGESPEED_API_KEY"),
            hint="Ключ — Google Cloud Console → APIs & Services → Credentials, с включённым PageSpeed Insights API.",
        ),
    ),
    login_hint="Добавьте email сервисного аккаунта в Search Console → Настройки → Пользователи и разрешения "
    "каждого ресурса.",
    provider=GOOGLE,
)
GOOGLE_AUTH = GoogleAuth(PROFILE)

LOGIN_GOOGLE = PROFILE.login_cmd
LOGIN_PAGESPEED = PROFILE.api_key_login_cmd(PAGESPEED)


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


def service_account_source() -> tuple[str, str] | None:
    """(JSON ключа, источник) или None, если ключа нигде нет. Не проверяет содержимое."""
    found = GOOGLE_AUTH.find_service_account()
    return (found.value, found.source) if found else None


def load_service_account() -> dict[str, Any]:
    """Словарь ключа сервисного аккаунта; нет или битый — NotAuthorized с командой-исправлением."""
    return GOOGLE_AUTH.load_service_account()


def pagespeed_key() -> str | None:
    return GOOGLE_AUTH.api_key(PAGESPEED)


def google_credentials(*, readonly: bool = True) -> Any:
    """google-auth Credentials сервисного аккаунта (токен ещё не получен — это сделает первый запрос)."""
    return GOOGLE_AUTH.credentials([SCOPE_READONLY if readonly else SCOPE_FULL])


def refresh_token(creds: Any) -> str:
    """Получить/обновить access token. Отказ Google → NotAuthorized, сеть → ApiError."""
    try:
        return GOOGLE_AUTH.refresh(creds)
    except TokenRequestFailed as exc:
        raise ApiError(GOOGLE, f"не удалось получить токен: {exc.__cause__ or exc.message}") from exc


def auth_status(*, check: bool = False) -> AuthStatus:
    """Что есть из авторизации. Без check — без сети; check=True — ещё и получает токен у Google."""
    found = GOOGLE_AUTH.status()
    status = AuthStatus(
        google=found.state,
        pagespeed_key=found.api_keys[PAGESPEED],
        account=found.account,
        source=found.source,
        detail=found.detail,
    )
    if check and status.google == "ok":
        try:
            refresh_token(google_credentials())
        except NotAuthorized as exc:
            status.google = "expired"
            status.detail = exc.message
    return status
