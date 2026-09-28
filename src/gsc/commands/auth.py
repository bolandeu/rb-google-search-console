"""Команда `gsc auth` — общая реализация из google-oauth (login/logout/status [--check]).

Ключи — в общем слоте keychain всех Google-инструментов: `gsc auth login` авторизует
и остальные, `gsc auth logout` — выходит из всех. `auth status --json` — отчёт §8
стандарта tools; под `--check` — по одному дешёвому read-only запросу на ключ.
"""

from __future__ import annotations

import typer
from google_oauth.auth_command import make_auth_app

from .. import output
from ..core.auth import GOOGLE_AUTH, PAGESPEED
from ..core.errors import ApiError
from ..providers.google import CruxProvider, SearchConsoleProvider

# Origin, у которого в CrUX заведомо есть данные; 404 («нет данных») ключ тоже подтверждает.
_CRUX_PROBE_ORIGIN = "https://www.google.com"


def _check_search_console(ctx: typer.Context) -> None:
    """Список ресурсов — бесплатный запрос, доступный любому сервисному аккаунту."""
    SearchConsoleProvider().probe("webmasters/v3/sites")


def _check_pagespeed_key(ctx: typer.Context) -> None:
    """Ключ PSI проверяется запросом к Chrome UX Report (тот же ключ): PSI гоняет Lighthouse 10–60 с."""
    provider = CruxProvider()
    try:
        provider.probe(
            "./records:queryRecord", "POST", params={"key": provider.key}, json={"origin": _CRUX_PROBE_ORIGIN}
        )
    except ApiError as exc:
        if exc.status != 404:  # 404 — у origin нет данных, но ключ принят
            raise


app = make_auth_app(GOOGLE_AUTH, output, check=_check_search_console, api_key_checks={PAGESPEED: _check_pagespeed_key})
# Группа создана в google-oauth через typer.Typer; голый `gsc auth` должен печатать help (exit 0), а не usage error.
app.callback(invoke_without_command=True)(output.help_if_no_command)
