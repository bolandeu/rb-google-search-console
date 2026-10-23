"""Every error a command raises, with its exit code and error code, and the table of exit codes the Standard defines."""

from __future__ import annotations

# Общие ошибки — из google-oauth: `output.guard` ловит именно этот `CliError`,
# поэтому ошибки авторизации (ключи, keychain, токен) выводятся тем же конвертом,
# что и собственные ошибки gsc. Каждая несёт `code`, `message`, `action` и код выхода;
# всё прочее `output.guard` превращает в конверт `UNEXPECTED`.
from google_oauth.errors import (
    CliError,
    CredentialStoreUnavailable,
    CredentialsUnhealthy,
    InvalidArguments,
    NotAuthorized,
    TokenRequestFailed,
)

from .._distribution import DIST_NAME

__all__ = [
    "Aborted",
    "ApiError",
    "AuthRequired",
    "CliError",
    "CliTooOld",
    "CredentialStoreUnavailable",
    "CredentialsUnhealthy",
    "DependencyTooOld",
    "InvalidArguments",
    "NotAuthorized",
    "ProjectNotInitialized",
    "PropertyNotFound",
    "ProviderError",
    "QuotaExceeded",
    "TokenRequestFailed",
]

# The command (same as the package name) for `action` hints; `uv tool upgrade`
# takes the distribution name, which differs (standard §10).
_CLI = __name__.split(".")[0]
_DIST = DIST_NAME

# Every exit code a generated CLI uses and what it means — the same table as in
# the Standard, Errors, and `describe --json`'s `exitCodes`. tests/test_describe.py
# fails when a CliError below uses a code that isn't listed here.
EXIT_CODES: dict[int, str] = {
    0: "Success",
    1: "General error (incl. UNEXPECTED and ABORTED)",
    2: "Invalid arguments",
    3: "Authentication error",
    4: "Project not initialized",
    5: "Provider error (external service: network, timeout, 5xx, 429, bad body)",
    6: "CLI too old for this project or database",
}


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


class DependencyTooOld(CliError):
    """Another CLI this one calls is missing or older than required (core/deps.py).

    `dist` is its distribution name — what `uv tool` knows it by (`rb-serp`
    for the `serp` command). With `install_url` the action is a
    pinned, runnable install; without it, what to install and no fake URL.
    """

    def __init__(
        self,
        name: str,
        installed: str | None,
        required: str | None,
        *,
        install_url: str | None = None,
        dist: str | None = None,
    ) -> None:
        dist = dist or name
        found = "is not installed" if installed is None else f"is {installed}"
        need = f"{name} >= {required}" if required else name
        if install_url:
            repo = install_url.removesuffix(".git")
            tag = f"v{required}" if required else "<latest release tag>"
            action = f"Run 'uv tool install \"{dist} @ git+{repo}.git@{tag}\" --force', then retry."
        elif installed is not None:
            action = f"Run 'uv tool upgrade {dist}', then retry."
        else:
            action = f"Install {need} (distribution {dist}; see its README for the install command), then retry."
        super().__init__(
            "DEPENDENCY_TOO_OLD",
            f"'{name}' {found}; {_CLI} needs {need}.",
            action=action,
            exit_code=1,
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
            action=f"Run 'uv tool upgrade {_DIST}' (or lower cli.min_version in the project's config.toml).",
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
