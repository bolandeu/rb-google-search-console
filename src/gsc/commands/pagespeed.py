from __future__ import annotations

import typer

from .. import output
from ..core import services
from ..core.errors import InvalidArguments
from ..core.models import Crux, PageSpeedError, PageSpeedResult
from ..core.pagespeed import CATEGORIES


def _score_color(score: float | None) -> str:
    if score is None:
        return "dim"
    return "green" if score >= 0.9 else "yellow" if score >= 0.5 else "red"


def _crux_line(title: str, crux: Crux | None) -> None:
    if crux is None:
        return
    parts = []
    for name in ("lcp", "inp", "cls", "fcp", "ttfb"):
        metric = getattr(crux, name)
        if metric is not None and metric.value is not None:
            value = f"{metric.value:.2f}" if name == "cls" else f"{metric.value:.0f} мс"
            share = f", хороших {metric.good * 100:.0f}%" if metric.good is not None else ""
            parts.append(f"{name.upper()} {value} ({metric.category or '?'}{share})")
    output.human.echo(f"  {title}: " + ("; ".join(parts) or "нет данных"))


def _render(results: list[PageSpeedResult | PageSpeedError], show_audits: bool) -> None:
    for r in results:
        if isinstance(r, PageSpeedError):
            output.human.err_console.print(f"[red]{r.url}[/red]: {r.message}")
            continue
        output.human.echo(f"\n[bold]{r.final_url or r.url}[/bold] ({r.strategy}, Lighthouse {r.lighthouse_version})")
        if r.runtime_error:
            output.human.err_console.print(f"[red]Lighthouse не смог замерить страницу: {r.runtime_error}[/red]")
        for warning in r.run_warnings:
            output.human.err_console.print(f"[yellow]Предупреждение замера: {warning}[/yellow]")
        for cat, score in r.scores.items():
            shown = f"{score * 100:.0f}" if score is not None else "—"
            output.human.echo(f"  [{_score_color(score)}]{cat}: {shown}[/{_score_color(score)}]")
        lab = r.lab
        lab_parts = [
            f"{name} {value:.0f} мс"
            for name, value in (
                ("LCP", lab.lcp_ms),
                ("FCP", lab.fcp_ms),
                ("TBT", lab.tbt_ms),
                ("SI", lab.speed_index_ms),
                ("TTI", lab.tti_ms),
            )
            if value is not None
        ]
        if lab.cls is not None:
            lab_parts.append(f"CLS {lab.cls:.3f}")
        output.human.echo("  Лаборатория: " + ("; ".join(lab_parts) or "—"))
        _crux_line("Пользователи (URL)", r.crux_url)
        _crux_line("Пользователи (origin)" + (", по URL данных нет" if r.crux_origin_fallback else ""), r.crux_origin)
        if show_audits:
            failed = [
                a
                for a in r.audits
                if a.score is not None and a.score < 0.9 and a.score_display_mode not in ("informative", "manual")
            ]
            for a in sorted(failed, key=lambda a: a.score or 0):
                value = f" — {a.display_value}" if a.display_value else ""
                output.human.echo(f"  [{_score_color(a.score)}]✗[/{_score_color(a.score)}] {a.id}: {a.title}{value}")


@output.guard
def pagespeed(
    ctx: typer.Context,
    urls: list[str] = typer.Argument(..., help="Один или несколько URL."),
    strategy: str = typer.Option("mobile", "--strategy", help="mobile или desktop."),
    categories: str = typer.Option(
        ",".join(CATEGORIES),
        "--categories",
        "-c",
        help="Через запятую: performance, accessibility, best-practices, seo (все — одна единица квоты).",
    ),
    screenshots: bool = typer.Option(
        False, "--screenshots", help="В --json добавить скриншоты (base64, сотни КБ на страницу)."
    ),
    locale: str | None = typer.Option(None, "--locale", help="Язык текстов аудитов (ru, en, …)."),
    audits: bool = typer.Option(False, "--audits", help="В консоли показать проваленные аудиты."),
    concurrency: int = typer.Option(4, "--concurrency", help="Сколько URL анализировать параллельно."),
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """PageSpeed Insights: оценки Lighthouse, лабораторные метрики, CrUX (реальные пользователи), аудиты.

    Нужен API-ключ PageSpeed (`gsc auth login --provider pagespeed`) — без ключа
    квота Google нулевая. Лимит ключа (400 запросов за 100 с) gsc соблюдает сам.
    Ошибка по одному URL не останавливает остальные.

    --json: {"ok": true, "count", "results": [{url, final_url, strategy, fetch_time,
    lighthouse_version, scores: {категория: 0..1}, lab: {lcp_ms, fcp_ms, tbt_ms, cls,
    speed_index_ms, tti_ms}, crux_url, crux_origin: {lcp, inp, cls, fcp, ttfb:
    {percentile, value, category, good, needs_improvement, poor}}, crux_origin_fallback,
    category_titles, audits: [{id, title, description, score, score_display_mode,
    display_value, numeric_value, details, savings_ms, savings_bytes, metric_savings,
    categories: [{category, weight, group}], warnings, explanation, error_message}],
    stack_packs: [{id, title, descriptions: {audit_id: текст}}], entities: [{name,
    is_first_party, category, origins}], run_warnings, runtime_error,
    final_screenshot, full_page_screenshot} | {url, code, message, status}]}.
    runtime_error не пуст — Lighthouse не смог замерить страницу, цифрам не верить.

    \b
    Примеры:
      gsc pagespeed https://example.com
      gsc pagespeed https://example.com --strategy desktop -c performance,seo --audits
      gsc pagespeed https://example.com/a https://example.com/b --json > psi.json
    """
    if concurrency < 1:
        raise InvalidArguments("--concurrency должен быть ≥ 1.")
    cats = services.split_list(categories)
    client = services.pagespeed()
    if len(urls) == 1:
        results: list[PageSpeedResult | PageSpeedError] = [
            client.analyze(urls[0], strategy, cats, locale=locale, screenshots=screenshots)
        ]
    else:
        results = list(
            client.analyze_many(urls, strategy, cats, concurrency=concurrency, locale=locale, screenshots=screenshots)
        )
    output.emit_success(
        ctx,
        {"count": len(results), "results": [r.model_dump() for r in results]},
        render_human=lambda _: _render(results, audits),
    )
