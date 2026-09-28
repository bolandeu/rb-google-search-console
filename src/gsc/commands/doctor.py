from __future__ import annotations

from pathlib import Path

import typer

from .. import output
from ..core import auth as gauth
from ..core import services
from ..core.errors import CliTooOld
from ..core.models import ProjectConfig
from ..core.version import DEV_VERSION, installed_version
from ..credentials import manager as credentials


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

    start = Path(ctx.obj.get("project") or Path.cwd())
    output.vecho(ctx, f"Searching for a project root starting at: {start}")
    root = services.find_project_root(start)
    # Проект необязателен: без него ресурс передаётся через -s.
    checks.append({"name": "project", "ok": True, "detail": str(root) if root else "нет — ресурс передаётся через -s"})

    config: ProjectConfig | None = None
    if root is not None:
        try:
            config = services.load_config(root, check_compat=False)
            checks.append({"name": "config", "ok": True})
        except Exception as exc:
            checks.append({"name": "config", "ok": False, "detail": str(exc)})
    if config is not None:
        try:
            services.check_cli_compat(config)
            checks.append({"name": "cli_compat", "ok": True, "detail": f"project requires >= {config.cli.min_version}"})
        except CliTooOld as exc:
            checks.append({"name": "cli_compat", "ok": False, "detail": exc.message})

    checks.extend(_auth_checks())

    all_ok = all(check["ok"] for check in checks)
    output.emit_success(
        ctx, {"healthy": all_ok, "checks": checks}, render_human=lambda data: output.human.render_doctor(data["checks"])
    )
