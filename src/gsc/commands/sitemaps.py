from __future__ import annotations

import typer
from rich.table import Table

from .. import output
from ..core import services
from ._common import SiteOption, resolve_site


@output.guard
def sitemaps(
    ctx: typer.Context,
    site_url: str | None = SiteOption,
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Карты сайта ресурса: тип, ошибки, предупреждения, даты отправки.

    --json: {"ok": true, "site", "count", "sitemaps": [{path, type, errors, warnings,
    is_pending, is_sitemaps_index, last_submitted, last_downloaded, contents: [{type,
    submitted, indexed}]}]}; contents — сколько URL каждого типа (web, image, video) в карте.

    \b
    Пример:
      gsc sitemaps -s sc-domain:example.com
    """
    site = resolve_site(ctx, site_url)
    items = services.search_console().list_sitemaps(site)

    def render(_: dict) -> None:
        if not items:
            output.human.echo("[dim]Карт сайта нет[/dim]")
            return
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Карта", overflow="fold")
        table.add_column("Тип")
        table.add_column("Ошибки", justify="right")
        table.add_column("Предупр.", justify="right")
        table.add_column("URL в карте", justify="right")
        table.add_column("Отправлена")
        for s in items:
            submitted = ", ".join(f"{c.type}: {c.submitted}" for c in s.contents)
            table.add_row(s.path, s.type or "", str(s.errors), str(s.warnings), submitted, s.last_submitted or "")
        output.human.console.print(table)

    output.emit_success(
        ctx, {"site": site, "count": len(items), "sitemaps": [s.model_dump() for s in items]}, render_human=render
    )


@output.guard
def sitemap(
    ctx: typer.Context,
    feedpath: str = typer.Argument(..., help="Полный URL карты сайта."),
    site_url: str | None = SiteOption,
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Одна карта сайта: статус обработки, ошибки, даты.

    --json: {"ok": true, "site", "path", "type", "errors", "warnings", "is_pending",
    "is_sitemaps_index", "last_submitted", "last_downloaded", "contents": [{type, submitted, indexed}]}.

    \b
    Пример:
      gsc sitemap -s sc-domain:example.com https://example.com/sitemap.xml
    """
    site = resolve_site(ctx, site_url)
    item = services.search_console().get_sitemap(site, feedpath)
    output.emit_success(
        ctx,
        {"site": site, **item.model_dump()},
        render_human=lambda d: output.human.key_values(
            d["path"],
            {
                "Тип": d["type"] or "—",
                "Ошибки": d["errors"],
                "Предупреждения": d["warnings"],
                "В обработке": d["is_pending"],
                "Индекс карт": d["is_sitemaps_index"],
                "Отправлена": d["last_submitted"] or "—",
                "Загружена Google": d["last_downloaded"] or "—",
                **{f"URL ({c['type']})": c["submitted"] for c in d["contents"]},
            },
        ),
    )


@output.guard
def submit_sitemap(
    ctx: typer.Context,
    feedpath: str = typer.Argument(..., help="Полный URL карты сайта."),
    site_url: str | None = SiteOption,
    dry_run: bool = output.DryRunOption,
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Отправить карту сайта в Search Console (Google поставит её в очередь на обработку).

    Меняет состояние ресурса в Google (повторная отправка безвредна); --dry-run —
    только показать, что будет отправлено. Нужны права siteOwner/siteFullUser.

    --json: {"ok": true, "site", "sitemap", "submitted": true | false, "dry_run"}.

    \b
    Примеры:
      gsc submit-sitemap -s sc-domain:example.com https://example.com/sitemap.xml --dry-run
      gsc submit-sitemap -s sc-domain:example.com https://example.com/sitemap.xml
    """
    site = resolve_site(ctx, site_url)
    dry = output.is_dry_run(ctx)  # guard уже слил локальный --dry-run в ctx
    if not dry:
        services.search_console().submit_sitemap(site, feedpath)
    output.emit_success(
        ctx,
        {"site": site, "sitemap": feedpath, "submitted": not dry, "dry_run": dry},
        render_human=lambda d: output.human.echo(
            f"Будет отправлена: {d['sitemap']} → {d['site']}"
            if d["dry_run"]
            else f"[green]Отправлена: {d['sitemap']}[/green]"
        ),
    )
