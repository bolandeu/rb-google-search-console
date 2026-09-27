from __future__ import annotations

import typer

from .. import output
from ..core import services
from ..core.errors import QuotaExceeded
from ..core.models import Inspection, InspectionError
from ._common import SiteOption, resolve_site


def _render(results: list[Inspection | InspectionError], remaining: int, stopped: str | None) -> None:
    for r in results:
        if isinstance(r, InspectionError):
            output.human.err_console.print(f"[red]{r.url}[/red]: {r.message}")
            continue
        pairs = {
            "Вердикт": r.verdict,
            "Покрытие": r.coverage_state,
            "Индексация": r.indexing_state,
            "robots.txt": r.robots_txt_state,
            "Загрузка": r.page_fetch_state,
            "Последний обход": r.last_crawl_time or "—",
            "Робот": r.crawled_as or "—",
            "Canonical Google": r.google_canonical or "—",
            "Canonical сайта": r.user_canonical or "—",
        }
        if r.sitemaps:
            pairs["Карты сайта"] = ", ".join(r.sitemaps)
        if r.referring_urls:
            pairs["Ссылаются"] = ", ".join(r.referring_urls[:5])
        if r.rich_results_verdict:
            pairs["Расширенные результаты"] = f"{r.rich_results_verdict}: " + ", ".join(x.type for x in r.rich_results)
        output.human.key_values(r.url, pairs)
    output.human.echo(f"[dim]Осталось инспекций на сегодня (учёт gsc): {remaining}[/dim]")
    if stopped:
        output.human.err_console.print(f"[yellow]Остановлено: {stopped}[/yellow]")


@output.guard
def inspect(
    ctx: typer.Context,
    urls: list[str] = typer.Argument(..., help="Один или несколько URL внутри ресурса."),
    site_url: str | None = SiteOption,
    language: str = typer.Option("ru", "--language", help="Язык сообщений об ошибках Google (ru, en, …)."),
    raw: bool = typer.Option(False, "--raw", help="В --json добавить исходный ответ Google (raw)."),
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Инспекция URL: индексация, покрытие, canonical, robots.txt, карты сайта, расширенные результаты.

    Квота Google: 2000 инспекций в сутки и 600 в минуту на ресурс; темп gsc держит
    сам. Ошибка по одному URL не останавливает остальные. Кончилась дневная квота —
    то, что успели, всё равно выводится, с "quota_exhausted": true (если не успели
    ничего — PROVIDER_ERROR, exit 5).

    --json: {"ok": true, "site", "count", "results": [{url, verdict, coverage_state,
    indexing_state, robots_txt_state, page_fetch_state, last_crawl_time, crawled_as,
    google_canonical, user_canonical, sitemaps, referring_urls, rich_results, …} |
    {url, code, message, status}], "quota_remaining", "quota_exhausted"}.

    \b
    Примеры:
      gsc inspect -s sc-domain:example.com https://example.com/page
      gsc inspect -s sc-domain:example.com https://example.com/a https://example.com/b --json
    """
    site = resolve_site(ctx, site_url)
    client = services.search_console()
    results: list[Inspection | InspectionError] = []
    stopped: str | None = None
    try:
        for item in client.inspect_many(urls, site, language=language):
            results.append(item)
    except QuotaExceeded as exc:
        if not results:
            raise
        stopped = exc.message
    exclude = None if raw else {"raw"}
    remaining = client.quota_remaining(site)
    output.emit_success(
        ctx,
        {
            "site": site,
            "count": len(results),
            "results": [r.model_dump(exclude=exclude if isinstance(r, Inspection) else None) for r in results],
            "quota_remaining": remaining,
            "quota_exhausted": stopped is not None,
        },
        render_human=lambda _: _render(results, remaining, stopped),
    )
