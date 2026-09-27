from __future__ import annotations

# Общие ошибки — из google-oauth: `output.guard` ловит именно этот `CliError`,
# поэтому ошибки авторизации (ключи, keychain, токен) выводятся тем же конвертом,
# что и собственные ошибки gsc. Каждая несёт `code`, `message`, `action` и код выхода;
# всё прочее `output.guard` превращает в конверт `UNEXPECTED`.
from google_oauth.errors import (
    CliError,
    CredentialStoreUnavailable,
    InvalidArguments,
    NotAuthorized,
    TokenRequestFailed,
)

__all__ = [
    "Aborted",
    "ApiError",
    "AuthRequired",
    "CliError",
    "CliTooOld",
    "CredentialStoreUnavailable",
    "InvalidArguments",
    "NotAuthorized",
    "ProjectNotInitialized",
    "PropertyNotFound",
    "ProviderError",
    "QuotaExceeded",
    "TokenRequestFailed",
]

# Derived from this package's own name so error messages can name the real
# command without this module needing template substitution.
_CLI = __name__.split(".")[0]


class ProjectNotInitialized(CliError):
    def __init__(self, path: str) -> None:
        super().__init__(
            "PROJECT_NOT_INITIALIZED",
            f"No project found at or above '{path}'.",
            action=f"Run '{_CLI} init' in the project directory.",
            exit_code=4,
        )


class AuthRequired(NotAuthorized):
    """API отверг запрос как неавторизованный (401/403 в HttpProvider). Это тоже `NotAuthorized`."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            provider,
            f"Authentication is required for provider '{provider}'.",
            action=f"Run '{_CLI} auth login --provider {provider}'.",
        )


class ProviderError(CliError):
    """An external service failed: network, timeout, HTTP 5xx/429, malformed response.

    `status` is the HTTP status when there was one. Raised by
    `providers.HttpProvider` after its retries are exhausted — commands and
    services normally don't construct this themselves.
    """

    def __init__(self, provider: str, message: str, *, status: int | None = None, action: str | None = None) -> None:
        super().__init__(
            "PROVIDER_ERROR",
            f"Provider '{provider}': {message}",
            action=action or "Retry later; if it keeps failing, check the provider's status page.",
            exit_code=5,
        )
        self.provider = provider
        self.status = status

    def to_dict(self) -> dict:
        payload = super().to_dict()
        payload["provider"] = self.provider
        if self.status is not None:
            payload["status"] = self.status
        return payload


class CliTooOld(CliError):
    def __init__(self, installed: str, required: str) -> None:
        super().__init__(
            "CLI_TOO_OLD",
            f"This project requires {_CLI} >= {required}, but {installed} is installed.",
            action=f"Run 'uv tool upgrade {_CLI}' (or lower cli.min_version in the project's config.toml).",
            exit_code=6,
        )


class Aborted(CliError):
    def __init__(self, description: str) -> None:
        super().__init__("ABORTED", f"{description}: aborted by user.", exit_code=1)


# --- Ошибки публичного API библиотеки (gsc.NotAuthorized — из google-oauth, и др.) ---
# Они же — обычные CliError: CLI показывает их тем же конвертом и кодом выхода,
# а библиотечный потребитель ловит по типу.


class PropertyNotFound(CliError):
    """Ресурса нет в Search Console или у сервисного аккаунта нет к нему доступа."""

    def __init__(self, site_url: str, detail: str = "") -> None:
        super().__init__(
            "INVALID_ARGUMENTS",
            f"Ресурс '{site_url}' не найден или недоступен сервисному аккаунту" + (f": {detail}" if detail else "."),
            action=f"Проверьте список: '{_CLI} sites'. Если ресурса там нет — добавьте email сервисного аккаунта "
            f"('{_CLI} auth status') в Search Console → Настройки → Пользователи и разрешения.",
            exit_code=2,
        )
        self.site_url = site_url


class ApiError(ProviderError):
    """Ошибка API Google после повторов: сеть, 5xx, неожиданный 4xx. `status` — HTTP-код, если был."""


class QuotaExceeded(ApiError):
    """Квота API исчерпана. `retry_after` — через сколько секунд имеет смысл повторить; `daily` — дневная квота."""

    def __init__(self, provider: str, message: str, *, retry_after: float | None, daily: bool) -> None:
        super().__init__(
            provider,
            message,
            status=429,
            action=f"Дневная квота исчерпана — повторите после сброса (≈ через {int(retry_after or 0) // 3600} ч)."
            if daily
            else "Слишком частые запросы — повторите через минуту.",
        )
        self.retry_after = retry_after
        self.daily = daily

    def to_dict(self) -> dict:
        payload = super().to_dict()
        payload["retry_after"] = self.retry_after
        payload["daily"] = self.daily
        return payload
