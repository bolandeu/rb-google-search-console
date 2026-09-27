"""CLI-обёртка для rb-google-search-console."""

from __future__ import annotations

import json
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()
console = Console()


@click.group()
def main() -> None:
    """rb-gsc — Google Search Console + PageSpeed Insights."""


# ── Sites ────────────────────────────────────────────────────────────────────


@main.command()
@click.option("--output", "-o", default=None, type=click.Path(), help="Сохранить в JSON.")
def sites(output: str | None) -> None:
    """Список сайтов в Search Console.

    \b
      rb-gsc sites
      rb-gsc sites -o sites.json
    """
    from .core.client import GSCClient

    client = GSCClient()
    data = client.list_sites()

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("URL", overflow="fold")
    table.add_column("Доступ")
    for s in data:
        table.add_row(s.site_url, s.permission_level)
    console.print(table)

    if output:
        Path(output).write_text(
            json.dumps([s.model_dump() for s in data], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        console.print(f"[green]Сохранено в {output}[/green]")


# ── Search Analytics ─────────────────────────────────────────────────────────


@main.command()
@click.option("--site-url", "-s", required=True, help="URL сайта (sc-domain: или https://)")
@click.option("--start-date", default=None, help="Начало периода YYYY-MM-DD (по умолчанию -30 дней)")
@click.option("--end-date", default=None, help="Конец периода YYYY-MM-DD (по умолчанию -3 дня)")
@click.option("--dimensions", "-d", default=None, help="Срезы через запятую: query,page,device,country,date")
@click.option("--search-type", default="web", show_default=True, help="web|image|video|news|discover")
@click.option("--limit", "-n", default=25, show_default=True, type=int)
@click.option("--output", "-o", default=None, type=click.Path(), help="Сохранить в JSON.")
def analytics(
    site_url: str,
    start_date: str | None,
    end_date: str | None,
    dimensions: str | None,
    search_type: str,
    limit: int,
    output: str | None,
) -> None:
    """Поисковая аналитика — клики, показы, CTR, позиции.

    \b
      rb-gsc analytics -s sc-domain:example.com
      rb-gsc analytics -s sc-domain:example.com -d query,page --limit 50
      rb-gsc analytics -s sc-domain:example.com --start-date 2024-01-01 --end-date 2024-01-31
    """
    from .core.client import GSCClient

    client = GSCClient()
    dims = [d.strip() for d in dimensions.split(",")] if dimensions else None

    result = client.search_analytics_query(
        site_url=site_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=dims,
        search_type=search_type,
        row_limit=limit,
    )

    table = Table(show_header=True, header_style="bold cyan")
    if dims:
        for d in dims:
            table.add_column(d, overflow="fold")
    table.add_column("Клики", justify="right")
    table.add_column("Показы", justify="right")
    table.add_column("CTR", justify="right")
    table.add_column("Позиция", justify="right")

    for row in result.rows:
        cells = list(row.keys)
        cells.extend([
            str(int(row.clicks)),
            str(int(row.impressions)),
            f"{row.ctr * 100:.1f}%",
            f"{row.position:.1f}",
        ])
        table.add_row(*cells)
    console.print(table)
    console.print(f"[dim]Строк: {len(result.rows)}[/dim]")

    if output:
        Path(output).write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        console.print(f"[green]Сохранено в {output}[/green]")


# ── URL Inspection ───────────────────────────────────────────────────────────


@main.command()
@click.option("--site-url", "-s", required=True, help="URL сайта")
@click.argument("url")
def inspect(site_url: str, url: str) -> None:
    """Инспекция URL — статус индексации, покрытие, robots.txt.

    \b
      rb-gsc inspect -s sc-domain:example.com https://example.com/page
    """
    from .core.client import GSCClient

    client = GSCClient()
    result = client.inspect_url(url, site_url)

    console.print(f"\n[bold]URL Inspection: {url}[/bold]\n")
    console.print(f"  Verdict:       {result.verdict}")
    console.print(f"  Index status:  {result.index_status}")
    console.print(f"  Coverage:      {result.coverage_state}")
    console.print(f"  Robots.txt:    {result.robots_txt_state}")
    console.print(f"  Indexing:      {result.indexing_state}")
    console.print(f"  Last crawl:    {result.last_crawl_time}")
    console.print(f"  Fetch state:   {result.page_fetch_state}")
    console.print(f"  Crawled as:    {result.crawled_as}")
    if result.referring_urls:
        console.print(f"  Referring:     {', '.join(result.referring_urls[:5])}")


# ── Sitemaps ─────────────────────────────────────────────────────────────────


@main.command()
@click.option("--site-url", "-s", required=True, help="URL сайта (sc-domain: или https://)")
@click.argument("site_url_arg", required=False, default=None)
def site(site_url: str, site_url_arg: str | None) -> None:
    """Информация о конкретном сайте.

    \b
      rb-gsc site -s sc-domain:example.com
    """
    from .core.client import GSCClient

    client = GSCClient()
    url = site_url_arg or site_url
    s = client.get_site(url)
    console.print(f"\n[bold]{s.site_url}[/bold]")
    console.print(f"  Доступ: {s.permission_level}")


@main.command()
@click.option("--site-url", "-s", required=True, help="URL сайта")
def sitemaps(site_url: str) -> None:
    """Список карт сайта.

    \b
      rb-gsc sitemaps -s sc-domain:example.com
    """
    from .core.client import GSCClient

    client = GSCClient()
    data = client.list_sitemaps(site_url)

    if not data:
        console.print("[dim]Карты сайта не найдены[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Path", overflow="fold")
    table.add_column("Type")
    table.add_column("Ошибки", justify="right")
    table.add_column("Предупр.", justify="right")
    table.add_column("Последняя отправка")
    for s in data:
        table.add_row(s.path, s.type or "", str(s.errors), str(s.warnings), s.last_submitted or "")
    console.print(table)


@main.command()
@click.option("--site-url", "-s", required=True, help="URL сайта")
@click.argument("feedpath")
def sitemap(site_url: str, feedpath: str) -> None:
    """Информация о конкретной карте сайта.

    \b
      rb-gsc sitemap -s sc-domain:example.com https://example.com/sitemap.xml
    """
    from .core.client import GSCClient

    client = GSCClient()
    s = client.get_sitemap(site_url, feedpath)

    console.print(f"\n[bold]{s.path}[/bold]")
    console.print(f"  Type:              {s.type or 'N/A'}")
    console.print(f"  Ошибки:            {s.errors}")
    console.print(f"  Предупреждения:    {s.warnings}")
    console.print(f"  Pending:           {s.is_pending}")
    console.print(f"  Sitemaps index:    {s.is_sitemaps_index}")
    console.print(f"  Последняя отправка: {s.last_submitted or 'N/A'}")
    console.print(f"  Последняя загрузка: {s.last_downloaded or 'N/A'}")


@main.command()
@click.option("--site-url", "-s", required=True, help="URL сайта")
@click.argument("feedpath")
def submit_sitemap(site_url: str, feedpath: str) -> None:
    """Отправить карту сайта на индексацию.

    \b
      rb-gsc submit-sitemap -s sc-domain:example.com https://example.com/sitemap.xml
    """
    from .core.client import GSCClient

    client = GSCClient(readonly=False)
    client.submit_sitemap(site_url, feedpath)
    console.print(f"[green]Sitemap отправлена: {feedpath}[/green]")


# ── PageSpeed ────────────────────────────────────────────────────────────────


@main.command()
@click.argument("url")
@click.option("--strategy", default="mobile", show_default=True, help="desktop|mobile")
@click.option("--categories", "-c", default=None, help="Категории: performance,accessibility,best-practices,seo")
@click.option("--locale", default=None, help="Локаль (напр. ru)")
@click.option("--output", "-o", default=None, type=click.Path(), help="Сохранить в JSON.")
def pagespeed(url: str, strategy: str, categories: str | None, locale: str | None, output: str | None) -> None:
    """PageSpeed Insights — анализ производительности.

    \b
      rb-gsc pagespeed https://example.com
      rb-gsc pagespeed https://example.com --strategy desktop -c performance,seo
    """
    from .core.pagespeed import PageSpeedClient

    client = PageSpeedClient()
    cats = [c.strip() for c in categories.split(",")] if categories else None
    result = client.analyze_url(url, strategy=strategy, categories=cats, locale=locale)

    console.print(f"\n[bold]PageSpeed: {result.url}[/bold] ({result.strategy})\n")

    for cat in result.categories:
        score = f"{cat.score * 100:.0f}" if cat.score is not None else "N/A"
        color = "green" if cat.score and cat.score >= 0.9 else ("yellow" if cat.score and cat.score >= 0.5 else "red")
        console.print(f"  [{color}]{cat.title}: {score}[/{color}]")

    m = result.metrics
    console.print(f"\n  FCP:  {m.first_contentful_paint:.0f} ms" if m.first_contentful_paint else "")
    console.print(f"  LCP:  {m.largest_contentful_paint:.0f} ms" if m.largest_contentful_paint else "")
    console.print(f"  TBT:  {m.total_blocking_time:.0f} ms" if m.total_blocking_time else "")
    console.print(f"  CLS:  {m.cumulative_layout_shift:.3f}" if m.cumulative_layout_shift is not None else "")
    console.print(f"  SI:   {m.speed_index:.0f} ms" if m.speed_index else "")

    if output:
        Path(output).write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        console.print(f"\n[green]Сохранено в {output}[/green]")


# ── MCP ──────────────────────────────────────────────────────────────────────


@main.command()
def mcp() -> None:
    """Запустить MCP-сервер."""
    from .mcp_server import serve
    serve()
