from __future__ import annotations

import typer
from rich.table import Table

from .. import output
from ..core import services
from ..core.errors import InvalidArguments
from ..core.models import CruxHistory, CruxRecord

# Основные метрики — в таком порядке в человеческом выводе; остальные (LCP-фазы, RTT) — после.
_MAIN = (
    "largest_contentful_paint",
    "interaction_to_next_paint",
    "cumulative_layout_shift",
    "first_contentful_paint",
    "experimental_time_to_first_byte",
)


def _fmt(name: str, value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}" if name == "cumulative_layout_shift" else f"{value:.0f} мс"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _ordered(names: list[str]) -> list[str]:
    return [n for n in _MAIN if n in names] + [n for n in names if n not in _MAIN]


def _render_record(r: CruxRecord) -> None:
    period = f"{r.period.first_date} — {r.period.last_date}" if r.period else ""
    table = Table(
        show_header=True, header_style="bold cyan", title=f"{r.url or r.origin} {r.form_factor or ''} {period}"
    )
    table.add_column("Метрика")
    table.add_column("p75", justify="right")
    table.add_column("Хорошо", justify="right")
    table.add_column("Средне", justify="right")
    table.add_column("Плохо", justify="right")
    for name in _ordered(list(r.metrics)):
        m = r.metrics[name]
        if m.fractions:
            shares = ", ".join(f"{k} {_pct(v)}" for k, v in m.fractions.items())
            table.add_row(name, shares, "", "", "")
            continue
        table.add_row(name, _fmt(name, m.p75), _pct(m.good), _pct(m.needs_improvement), _pct(m.poor))
    output.human.console.print(table)


def _render_history(h: CruxHistory) -> None:
    if not h.periods:
        output.human.echo("[dim]Нет периодов[/dim]")
        return
    title = f"{h.url or h.origin} {h.form_factor or ''}: {h.periods[0].last_date} → {h.periods[-1].last_date}"
    table = Table(show_header=True, header_style="bold cyan", title=title)
    table.add_column("Метрика")
    table.add_column("p75 тогда", justify="right")
    table.add_column("p75 сейчас", justify="right")
    table.add_column("Хороших тогда", justify="right")
    table.add_column("Хороших сейчас", justify="right")
    for name in _ordered(list(h.metrics)):
        m = h.metrics[name]
        if not m.p75:
            continue
        table.add_row(
            name,
            _fmt(name, m.p75[0]),
            _fmt(name, m.p75[-1]),
            _pct(m.good[0] if m.good else None),
            _pct(m.good[-1] if m.good else None),
        )
    output.human.console.print(table)


@output.guard
def crux(
    ctx: typer.Context,
    url: str | None = typer.Argument(None, help="URL страницы (или --origin для сайта целиком)."),
    origin: str | None = typer.Option(None, "--origin", help="Сайт целиком: https://example.com (без пути)."),
    form_factor: str | None = typer.Option(
        None, "--form-factor", help="phone, desktop или tablet; по умолчанию — все устройства вместе."
    ),
    history: bool = typer.Option(False, "--history", help="История по неделям вместо последних 28 дней."),
    periods: int = typer.Option(25, "--periods", help="С --history: сколько недель (1–40)."),
    metrics: str | None = typer.Option(
        None, "--metrics", help="Только эти метрики CrUX через запятую (largest_contentful_paint, …)."
    ),
    json_output: bool = output.JsonOption,
    quiet: bool = output.QuietOption,
) -> None:
    """Chrome UX Report: реальные посетители Chrome — Core Web Vitals, доли хороших визитов, история.

    Данные только у страниц и сайтов с заметным трафиком из Chrome; нет данных —
    "record": null (exit 0). Кроме LCP/INP/CLS/FCP/TTFB: фазы LCP (TTFB, задержка и
    длительность загрузки, отрисовка), round_trip_time, доли устройств (form_factors).
    Ключ — тот же, что у PageSpeed, с включённым Chrome UX Report API. Квота 150/мин.

    --json: {"ok": true, "record": {url, origin, form_factor, period: {first_date,
    last_date}, metrics: {имя: {p75, good, needs_improvement, poor, fractions}}} | null};
    с --history: {"ok": true, "history": {url, origin, form_factor, periods: [...],
    metrics: {имя: {p75: [...], good: [...], needs_improvement: [...], poor: [...],
    fractions}}} | null} — ряды от старых недель к новым.

    \b
    Примеры:
      gsc crux --origin https://example.com
      gsc crux https://example.com/ --form-factor phone
      gsc crux --origin https://example.com --history --periods 40 --json
    """
    if (url is None) == (origin is None):
        raise InvalidArguments("Укажите URL или --origin (что-то одно).")
    client = services.crux()
    names = services.split_list(metrics) or None
    if history:
        h = client.history(url, origin=origin, form_factor=form_factor, metrics=names, periods=periods)
        output.emit_success(
            ctx,
            {"history": h.model_dump() if h else None},
            render_human=lambda _: (
                _render_history(h) if h else output.human.echo("[yellow]У Google нет данных[/yellow]")
            ),
        )
        return
    r = client.record(url, origin=origin, form_factor=form_factor, metrics=names)
    output.emit_success(
        ctx,
        {"record": r.model_dump() if r else None},
        render_human=lambda _: _render_record(r) if r else output.human.echo("[yellow]У Google нет данных[/yellow]"),
    )
