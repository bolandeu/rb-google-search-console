from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

import typer

from .. import output
from ..core import auth as gauth
from ..core.errors import InvalidArguments
from ..credentials import manager as credentials

app = output.group("Доступы Google: ключ сервисного аккаунта и API-ключ PageSpeed (в связке ключей ОС).")


class Provider(StrEnum):
    google = gauth.GOOGLE
    pagespeed = gauth.PAGESPEED


ProviderOption = typer.Option(
    Provider.google, "--provider", help="google — сервисный аккаунт Search Console; pagespeed — API-ключ PSI."
)


def _login_google(file: Path | None, non_interactive: bool) -> dict:
    if file is not None:
        text = file.expanduser().read_text(encoding="utf-8")
    else:
        found = gauth.service_account_source()
        env_text = found[0] if found and found[1] in ("env", "file") else None
        if env_text:
            text = env_text
        elif non_interactive:
            raise InvalidArguments(
                "Нужен --file <service-account.json> (или GSC_GOOGLE_SERVICE_ACCOUNT_JSON в окружении): "
                "задан --non-interactive."
            )
        else:
            path = typer.prompt("Путь к JSON-ключу сервисного аккаунта")
            text = Path(path).expanduser().read_text(encoding="utf-8")
    info = gauth.parse_service_account(text)
    credentials.store_secret(gauth.GOOGLE, text, gauth.SA_FIELD)
    return {"provider": gauth.GOOGLE, "account": info["client_email"]}


def _login_pagespeed(non_interactive: bool) -> dict:
    key = credentials.read_secret_from_env(gauth.PAGESPEED) or os.environ.get("GOOGLE_PAGESPEED_API_KEY")
    if not key:
        if non_interactive:
            raise InvalidArguments("Нет GSC_PAGESPEED_API_KEY в окружении, а задан --non-interactive.")
        key = typer.prompt("API-ключ PageSpeed Insights", hide_input=True)
    credentials.store_secret(gauth.PAGESPEED, key.strip())
    return {"provider": gauth.PAGESPEED, "account": None}


@app.command("login")
@output.guard
def login(
    ctx: typer.Context,
    provider: Provider = ProviderOption,
    file: Path | None = typer.Option(
        None, "--file", "-f", exists=True, dir_okay=False, help="google: JSON-ключ сервисного аккаунта."
    ),
    non_interactive: bool = output.NonInteractiveOption,
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Сохранить доступ в связку ключей ОС (gsc:google / gsc:pagespeed).

    google: содержимое JSON-ключа сервисного аккаунта — из --file, иначе из
    GSC_GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_SERVICE_ACCOUNT_FILE,
    иначе спросит путь. После входа добавьте email аккаунта (есть в выводе) в Search
    Console → Настройки → Пользователи и разрешения каждого ресурса.

    pagespeed: API-ключ из GSC_PAGESPEED_API_KEY / GOOGLE_PAGESPEED_API_KEY, иначе
    спросит скрытым вводом. Ключ — Google Cloud Console → APIs & Services → Credentials,
    с включённым PageSpeed Insights API.

    --json: {"ok": true, "provider", "account"}.

    \b
    Примеры:
      gsc auth login --file ~/Downloads/gsc-reader.json
      gsc auth login --provider pagespeed
    """
    non_int = bool(ctx.obj.get("non_interactive") or non_interactive)
    result = _login_google(file, non_int) if provider is Provider.google else _login_pagespeed(non_int)
    output.emit_success(
        ctx,
        result,
        render_human=lambda d: output.human.echo(
            f"Сохранено: {d['provider']}" + (f" — сервисный аккаунт {d['account']}" if d["account"] else "")
        ),
    )


@app.command("logout")
@output.guard
def logout(
    ctx: typer.Context,
    provider: Provider = ProviderOption,
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Удалить доступ из связки ключей ОС (переменные окружения не трогает).

    --json: {"ok": true, "provider"}.
    """
    credentials.delete_secret(provider.value)
    output.emit_success(
        ctx,
        {"provider": provider.value},
        render_human=lambda d: output.human.echo(f"Удалено из связки ключей: {d['provider']}"),
    )


@app.command("status")
@output.guard
def auth_status(
    ctx: typer.Context,
    check: bool = typer.Option(False, "--check", help="Ещё и получить токен у Google — проверка, что ключ не отозван."),
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Что есть из доступов: сервисный аккаунт (email, откуда взят) и ключ PageSpeed.

    google: ok | missing | expired (expired — только с --check: Google отверг ключ).

    --json: {"ok": true, "google", "pagespeed_key", "account", "source", "detail"}.
    """
    status = gauth.auth_status(check=check)
    output.emit_success(
        ctx,
        status.model_dump(),
        render_human=lambda d: output.human.key_values(
            "Доступы",
            {
                "Search Console": d["google"] + (f" ({d['account']}, {d['source']})" if d["account"] else ""),
                "PageSpeed": "ключ есть" if d["pagespeed_key"] else "ключа нет — gsc auth login --provider pagespeed",
                **({"Подробности": d["detail"]} if d["detail"] else {}),
            },
        ),
    )
