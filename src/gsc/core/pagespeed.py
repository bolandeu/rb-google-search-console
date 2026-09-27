"""PageSpeed Insights v5: полный разбор ответа — CrUX (URL и origin), оценки, метрики, все аудиты Lighthouse."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any

import httpx

from ..providers.google import PageSpeedProvider
from .errors import ApiError, InvalidArguments, QuotaExceeded
from .models import Audit, Crux, CruxMetric, LabMetrics, PageSpeedError, PageSpeedResult
from .quota import PAGESPEED_PER_100S, RateLimiter

STRATEGIES = ("mobile", "desktop")
CATEGORIES = ("performance", "accessibility", "best-practices", "seo")

# Ключи метрик CrUX в ответе PSI → поле модели.
_CRUX_KEYS = {
    "LARGEST_CONTENTFUL_PAINT_MS": "lcp",
    "INTERACTION_TO_NEXT_PAINT": "inp",
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": "cls",
    "FIRST_CONTENTFUL_PAINT_MS": "fcp",
    "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "ttfb",
}
_LAB_AUDITS = {
    "largest-contentful-paint": "lcp_ms",
    "first-contentful-paint": "fcp_ms",
    "total-blocking-time": "tbt_ms",
    "cumulative-layout-shift": "cls",
    "speed-index": "speed_index_ms",
    "interactive": "tti_ms",
}


def _crux(raw: dict | None) -> Crux | None:
    if not raw or not raw.get("metrics"):
        return None
    fields: dict[str, Any] = {}
    for key, name in _CRUX_KEYS.items():
        metric = raw["metrics"].get(key)
        if not metric:
            continue
        percentile = metric.get("percentile")
        value = percentile / 100 if name == "cls" and percentile is not None else percentile
        fields[name] = CruxMetric(percentile=percentile, value=value, category=metric.get("category"))
    return Crux(id=raw.get("id", ""), overall_category=raw.get("overall_category"), **fields)


def _audit(audit_id: str, raw: dict) -> Audit:
    details = raw.get("details") or {}
    items = details.get("items")
    return Audit(
        id=raw.get("id", audit_id),
        title=raw.get("title", ""),
        score=raw.get("score"),
        score_display_mode=raw.get("scoreDisplayMode", ""),
        display_value=raw.get("displayValue"),
        numeric_value=raw.get("numericValue"),
        numeric_unit=raw.get("numericUnit"),
        details_type=details.get("type"),
        details=items if isinstance(items, list) else [],
        savings_ms=details.get("overallSavingsMs"),
        savings_bytes=details.get("overallSavingsBytes"),
        metric_savings={k: v for k, v in (raw.get("metricSavings") or {}).items() if isinstance(v, int | float)},
    )


def parse_pagespeed(url: str, strategy: str, data: dict) -> PageSpeedResult:
    """Ответ runPagespeed → PageSpeedResult."""
    lh = data.get("lighthouseResult", {})
    audits_raw: dict = lh.get("audits", {})
    loading = data.get("loadingExperience")
    fallback = bool(loading and loading.get("origin_fallback"))
    lab = {
        field: audits_raw[audit_id].get("numericValue")
        for audit_id, field in _LAB_AUDITS.items()
        if audit_id in audits_raw
    }
    return PageSpeedResult(
        url=url,
        final_url=lh.get("finalDisplayedUrl") or lh.get("finalUrl") or lh.get("requestedUrl") or data.get("id", ""),
        strategy=strategy,
        fetch_time=lh.get("fetchTime", ""),
        lighthouse_version=lh.get("lighthouseVersion", ""),
        scores={cat_id: cat.get("score") for cat_id, cat in lh.get("categories", {}).items()},
        lab=LabMetrics(**lab),
        crux_url=None if fallback else _crux(loading),
        crux_origin=_crux(data.get("originLoadingExperience")),
        crux_origin_fallback=fallback,
        audits=[_audit(audit_id, raw) for audit_id, raw in audits_raw.items()],
    )


class PageSpeed:
    """Клиент PageSpeed Insights. Ключ — из `gsc auth login --provider pagespeed` / env; создание без побочных эффектов."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._api = PageSpeedProvider(api_key=api_key, transport=transport)
        self._limiter = limiter or RateLimiter(PAGESPEED_PER_100S, 100.0)

    def analyze(
        self,
        url: str,
        strategy: str = "mobile",
        categories: Sequence[str] = ("performance",),
        *,
        locale: str | None = None,
    ) -> PageSpeedResult:
        if strategy not in STRATEGIES:
            raise InvalidArguments(f"strategy — {' или '.join(STRATEGIES)}, а не '{strategy}'.")
        unknown = [c for c in categories if c not in CATEGORIES]
        if unknown:
            raise InvalidArguments(f"Неизвестные категории: {', '.join(unknown)}. Доступны: {', '.join(CATEGORIES)}.")
        self._limiter.acquire()
        data = self._api.run(url, strategy=strategy, categories=list(categories), locale=locale)
        return parse_pagespeed(url, strategy, data)

    def analyze_many(
        self,
        urls: Iterable[str],
        strategy: str = "mobile",
        categories: Sequence[str] = ("performance",),
        *,
        concurrency: int = 4,
        locale: str | None = None,
    ) -> Iterator[PageSpeedResult | PageSpeedError]:
        """Параллельный анализ; результаты — по мере готовности, не в порядке urls.

        Темп держится в пределах лимита ключа (400 за 100 с), 429/5xx повторяются.
        Ошибка по URL → PageSpeedError, обход продолжается; нет ключа / дневная
        квота → исключение из итератора (выданное до этого уже у вызывающего).
        В работе одновременно не больше 2×concurrency URL — список может быть любым.
        """
        pending: dict[Future, str] = {}
        source = iter(urls)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            try:
                while True:
                    for url in itertools.islice(source, 2 * concurrency - len(pending)):
                        pending[pool.submit(self.analyze, url, strategy, categories, locale=locale)] = url
                    if not pending:
                        return
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        url = pending.pop(future)
                        try:
                            yield future.result()
                        except QuotaExceeded as exc:
                            if exc.daily:
                                raise
                            yield PageSpeedError(url=url, code=exc.code, message=exc.message, status=exc.status)
                        except ApiError as exc:
                            yield PageSpeedError(url=url, code=exc.code, message=exc.message, status=exc.status)
            finally:
                for future in pending:
                    future.cancel()
