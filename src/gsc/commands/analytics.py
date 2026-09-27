from __future__ import annotations

import typer
from rich.table import Table

from .. import output
from ..core import services
from ..core.search_console import default_range
from ._common import SiteOption, resolve_site


@output.guard
def analytics(
    ctx: typer.Context,
    site_url: str | None = SiteOption,
    start_date: str | None = typer.Option(None, "--start-date", help="Начало периода YYYY-MM-DD."),
    end_date: str | None = typer.Option(None, "--end-date", help="Конец периода YYYY-MM-DD."),
    dimensions: str = typer.Option(
        "query",
        "--dimensions",
        "-d",
        help="Срезы через запятую: query, page, device, country, date, hour, searchAppearance.",
    ),
    search_type: str = typer.Option("web", "--search-type", help="web, image, video, news, discover, googleNews."),
    data_state: str = typer.Option(
        "final",
        "--data-state",
        help="final — только устоявшиеся данные; all — со свежими; hourly_all — почасовые (со срезом hour).",
    ),
    filters: list[str] = typer.Option(
        [],
        "--filter",
        "-f",
        help="Фильтр СРЕЗ:ОПЕРАТОР:ВЫРАЖЕНИЕ, можно повторять (все условия сразу). Операторы: equals, "
        "notEquals, contains, notContains, includingRegex, excludingRegex. Пример: page:contains:/blog/.",
    ),
    aggregation: str | None = typer.Option(
        None,
        "--aggregation",
        help="Как считать клики/показы: byPage — по страницам, byProperty — по сайту; по умолчанию решает Google.",
    ),
    by_day: bool = typer.Option(
        False,
        "--by-day",
        help="Отдельный запрос на каждый день: обходит предел Google ~50 000 строк на запрос; строки подневные.",
    ),
    limit: int = typer.Option(25, "--limit", "-n", help="Сколько строк; 0 — все (постранично по 25 000)."),
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Поисковая аналитика: клики, показы, CTR, средняя позиция по срезам.

    Период по умолчанию — последние 28 дней, заканчивая 3 днями раньше сегодня
    (данные Search Console приходят с задержкой). URL в ответе — как их отдаёт Google.

    Google отдаёт не больше ~50 000 строк на запрос — для полного page×query на
    большом сайте нужен --by-day (строки тогда по дням, в keys есть date).

    --json: {"ok": true, "site", "start_date", "end_date", "dimensions", "count",
    "first_incomplete_date", "rows": [{keys: {срез: значение}, clicks, impressions, ctr,
    position}]}; first_incomplete_date — с какой даты данные неполные (при --data-state all).

    \b
    Примеры:
      gsc analytics -s sc-domain:example.com
      gsc analytics -s sc-domain:example.com -d page,query --limit 100
      gsc analytics -s sc-domain:example.com -d page --limit 0 --json > pages.json
      gsc analytics -s sc-domain:example.com --start-date 2026-01-01 --end-date 2026-01-31
      gsc analytics -s sc-domain:example.com -d page,query -f page:contains:/blog/ -f country:equals:rus
      gsc analytics -s sc-domain:example.com -d page,query --by-day --limit 0 --json > full.json
    """
    site = resolve_site(ctx, site_url)
    dims = services.split_list(dimensions)
    d_start, d_end = default_range()
    start, end = start_date or d_start.isoformat(), end_date or d_end.isoformat()
    iterator = services.search_console().iter_search_analytics(
        site,
        start,
        end,
        dims,
        search_type=search_type,
        data_state=data_state,
        filters=[services.parse_filter(f) for f in filters] or None,
        aggregation_type=aggregation,
        by_day=by_day,
        limit=limit or None,
    )
    rows = list(iterator)

    def render(_: dict) -> None:
        table = Table(show_header=True, header_style="bold cyan", title=f"{site}: {start} — {end}")
        for d in dims:
            table.add_column(d, overflow="fold")
        for name in ("Клики", "Показы", "CTR", "Позиция"):
            table.add_column(name, justify="right")
        for row in rows:
            table.add_row(
                *(row.keys.get(d, "") for d in dims),
                str(row.clicks),
                str(row.impressions),
                f"{row.ctr * 100:.1f}%",
                f"{row.position:.1f}",
            )
        output.human.console.print(table)
        output.human.echo(f"[dim]Строк: {len(rows)}[/dim]")

    output.emit_success(
        ctx,
        {
            "site": site,
            "start_date": start,
            "end_date": end,
            "dimensions": dims,
            "count": len(rows),
            "first_incomplete_date": iterator.first_incomplete_date,
            "rows": [r.model_dump() for r in rows],
        },
        render_human=render,
    )
