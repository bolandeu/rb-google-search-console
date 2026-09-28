from __future__ import annotations

import typer
from rich.table import Table

from .. import output
from ..core import services
from ._common import SiteOption, resolve_site


@output.guard
def sites(
    ctx: typer.Context,
    for_url: str | None = typer.Option(
        None, "--for", help="Показать только ресурс, который покрывает этот URL (доменный важнее URL-prefix)."
    ),
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Ресурсы Search Console, доступные сервисному аккаунту.

    С --for URL — какой ресурс покрывает URL: доменный (sc-domain:) предпочтительнее,
    среди URL-prefix — самый длинный подходящий; нет такого → "site": null.

    --json: {"ok": true, "count": N, "sites": [{site_url, permission_level, kind}]};
    с --for: {"ok": true, "url": …, "site": "sc-domain:…" | null}.

    \b
    Ещё примеры:
      {cli} sites --for https://blog.example.com/post --json

    Example: {cli} sites
    """
    client = services.search_console()
    if for_url:
        site = client.property_for(for_url)
        output.emit_success(
            ctx,
            {"url": for_url, "site": site},
            render_human=lambda d: output.human.echo(d["site"] or "[yellow]Ни один ресурс не покрывает URL[/yellow]"),
        )
        return
    props = client.list_properties()

    def render(_: dict) -> None:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Ресурс", overflow="fold")
        table.add_column("Тип")
        table.add_column("Доступ")
        for p in props:
            table.add_row(p.site_url, p.kind, p.permission_level)
        output.human.console.print(table)

    output.emit_success(
        ctx,
        {"count": len(props), "sites": [{**p.model_dump(), "kind": p.kind} for p in props]},
        render_human=render,
    )


@output.guard
def site(
    ctx: typer.Context,
    site_url: str | None = SiteOption,
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Проверить доступ к одному ресурсу: уровень прав.

    Нет доступа → INVALID_ARGUMENTS (exit 2) с подсказкой, кого добавить в Search Console.

    --json: {"ok": true, "site_url", "permission_level", "kind"}.

    Example: {cli} site -s sc-domain:example.com
    """
    prop = services.search_console().get_property(resolve_site(ctx, site_url))
    output.emit_success(
        ctx,
        {**prop.model_dump(), "kind": prop.kind},
        render_human=lambda d: output.human.key_values(
            d["site_url"], {"Доступ": d["permission_level"], "Тип": d["kind"]}
        ),
    )
