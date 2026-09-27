"""Аутентификация для Google Search Console API."""

from __future__ import annotations

import json
import os
from pathlib import Path

_SCOPES_RO = ["https://www.googleapis.com/auth/webmasters.readonly"]
_SCOPES_RW = ["https://www.googleapis.com/auth/webmasters"]


def credentials_from_service_account(
    path: str | Path | None = None,
    json_str: str | None = None,
    *,
    readonly: bool = True,
) -> "google.oauth2.service_account.Credentials":
    """Создать credentials из service account JSON.

    Args:
        path: путь к JSON-файлу (или env GOOGLE_SERVICE_ACCOUNT_FILE)
        json_str: JSON-строка (или env GOOGLE_SERVICE_ACCOUNT_JSON)
        readonly: если False — полный доступ (submit sitemaps, etc.)
    """
    from google.oauth2 import service_account

    scopes = _SCOPES_RO if readonly else _SCOPES_RW

    if json_str:
        info = json.loads(json_str)
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)

    resolved = path or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if resolved:
        return service_account.Credentials.from_service_account_file(str(resolved), scopes=scopes)

    env_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if env_json:
        info = json.loads(env_json)
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)

    raise RuntimeError(
        "Не задан service account. Укажите path/json_str или env: "
        "GOOGLE_SERVICE_ACCOUNT_FILE / GOOGLE_SERVICE_ACCOUNT_JSON"
    )


def credentials_from_oauth(
    client_secrets_path: str | Path,
    *,
    readonly: bool = True,
    port: int = 8080,
) -> "google.oauth2.credentials.Credentials":
    """OAuth2 flow (открывает браузер). Для интерактивного использования."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    scopes = _SCOPES_RO if readonly else _SCOPES_RW
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), scopes=scopes)
    return flow.run_local_server(port=port)
