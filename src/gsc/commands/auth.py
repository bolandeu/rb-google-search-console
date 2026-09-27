"""Команда `gsc auth` — общая реализация из google-oauth (login/logout/status [--check]).

Ключи — в общем слоте keychain всех Google-инструментов: `gsc auth login` авторизует
и остальные, `gsc auth logout` — выходит из всех.
"""

from __future__ import annotations

from google_oauth.auth_command import make_auth_app

from .. import output
from ..core.auth import GOOGLE_AUTH

app = make_auth_app(GOOGLE_AUTH, output)
# Группа создана в google-oauth через typer.Typer; голый `gsc auth` должен печатать help (exit 0), а не usage error.
app.callback(invoke_without_command=True)(output.help_if_no_command)
