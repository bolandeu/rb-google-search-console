"""Keychain ОС + переменные окружения — общая реализация из google-oauth.

Слот общий для всех Google-инструментов (`google-oauth:service_account`,
`google-oauth:api_key/<имя>`); ключи и порядок поиска — в `gsc.core.auth`.

`keyring` реэкспортирован намеренно: тесты подменяют
`gsc.credentials.manager.keyring.*` in-memory-хранилищем.
"""

from __future__ import annotations

from google_oauth.credentials import keyring  # noqa: F401 — патч-цель тестов

from ..core.auth import GOOGLE_AUTH

store = GOOGLE_AUTH.store
store_backend = store.backend
