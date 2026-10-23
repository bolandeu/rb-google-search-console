"""The `doctor` command: checks of this CLI's own setup, one line per check."""

from __future__ import annotations

import typer

from .. import output
from ..core import auth as gauth
from ..core import deps
from ..core.version import DEV_VERSION, installed_version, optional_module
from ..credentials import manager as credentials

_PACKAGE_NAME = __name__.split(".")[0]


def _auth_checks() -> list[dict]:
    backend = credentials.store_backend()
    checks: list[dict] = [
        {
            "name": "credential_store",
            "ok": backend is not None,
            "detail": backend or "нет связки ключей ОС — доступы только из переменных окружения",
        }
    ]
    status = gauth.auth_status()
    checks.append(
        {
            "name": "credential:google",
            "ok": status.google == "ok",
            "detail": f"{status.account} ({status.source})" if status.google == "ok" else status.detail,
        }
    )
    checks.append(
        {
            "name": "credential:pagespeed",
            "ok": status.pagespeed_key,
            "detail": None if status.pagespeed_key else f"нужен для pagespeed: '{gauth.LOGIN_PAGESPEED}'",
        }
    )
    return checks


@output.guard
def doctor(
    ctx: typer.Context,
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
    verbose: bool = output.VerboseOption,
) -> None:
    """Диагностика: версия, проект, настройки, связка ключей, доступы Google и PageSpeed.

    Без сети: ключ сервисного аккаунта проверяется разбором, а не запросом —
    живая проверка `gsc auth status --check`. Всегда завершается с кодом 0 —
    результат это сам отчёт; `healthy` говорит, прошли ли все проверки.

    --json: {"ok": true, "healthy", "checks": [{name, ok, detail}]}.

    Example: {cli} doctor --json
    """
    checks: list[dict] = [{"name": "python", "ok": True}]
    checks.append({"name": "cli_version", "ok": True, "detail": installed_version() or DEV_VERSION})

    if project := optional_module(f"{_PACKAGE_NAME}.commands.project"):  # include_project=false drops it
        checks.extend(project.doctor_checks(ctx))

    checks.extend(_auth_checks())
    checks.extend(deps.doctor_checks())  # [[tool.rb.external]] in pyproject.toml

    all_ok = all(check["ok"] for check in checks)
    output.emit_success(
        ctx, {"healthy": all_ok, "checks": checks}, render_human=lambda data: output.human.render_doctor(data["checks"])
    )
