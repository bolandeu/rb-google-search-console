"""PageSpeed Insights API клиент."""

from __future__ import annotations

import os

import httpx
from loguru import logger

from .models import (
    PageSpeedCategory,
    PageSpeedMetrics,
    PageSpeedParams,
    PageSpeedResult,
)

_API_URL = "https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed"


class PageSpeedClient:
    """Клиент PageSpeed Insights API v5."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("GOOGLE_PAGESPEED_API_KEY", "")

    def analyze(self, params: PageSpeedParams) -> PageSpeedResult:
        """Запустить анализ URL."""
        query: dict = {
            "url": params.url,
            "strategy": params.strategy,
        }
        if self._api_key:
            query["key"] = self._api_key
        if params.locale:
            query["locale"] = params.locale

        categories = params.categories or ["performance"]
        for cat in categories:
            query.setdefault("category", [])
            if isinstance(query["category"], list):
                query["category"].append(cat)
            else:
                query["category"] = [query["category"], cat]

        logger.info(f"PageSpeed: {params.url} ({params.strategy}) categories={categories}")

        resp = httpx.get(_API_URL, params=query, timeout=60)
        if not resp.is_success:
            raise RuntimeError(f"PageSpeed API error ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        return self._parse_response(data, params.strategy)

    def analyze_url(
        self,
        url: str,
        *,
        strategy: str = "mobile",
        categories: list[str] | None = None,
        locale: str | None = None,
    ) -> PageSpeedResult:
        """Упрощённый запрос анализа."""
        return self.analyze(PageSpeedParams(
            url=url, strategy=strategy, categories=categories, locale=locale,
        ))

    def _parse_response(self, data: dict, strategy: str) -> PageSpeedResult:
        lh = data.get("lighthouseResult", {})
        cats_raw = lh.get("categories", {})
        categories: list[PageSpeedCategory] = []
        overall_score: float | None = None

        for cat_id, cat_data in cats_raw.items():
            score = cat_data.get("score")
            categories.append(PageSpeedCategory(
                id=cat_id,
                title=cat_data.get("title", cat_id),
                score=score,
            ))
            if cat_id == "performance":
                overall_score = score

        audits = lh.get("audits", {})
        metrics = PageSpeedMetrics(
            first_contentful_paint=_audit_ms(audits, "first-contentful-paint"),
            largest_contentful_paint=_audit_ms(audits, "largest-contentful-paint"),
            total_blocking_time=_audit_ms(audits, "total-blocking-time"),
            cumulative_layout_shift=_audit_value(audits, "cumulative-layout-shift"),
            speed_index=_audit_ms(audits, "speed-index"),
            interactive=_audit_ms(audits, "interactive"),
        )

        return PageSpeedResult(
            url=lh.get("finalUrl", lh.get("requestedUrl", "")),
            strategy=strategy,
            categories=categories,
            metrics=metrics,
            overall_score=overall_score,
            lighthouse_version=lh.get("lighthouseVersion", ""),
            fetch_time=lh.get("fetchTime", ""),
        )


def _audit_ms(audits: dict, key: str) -> float | None:
    audit = audits.get(key)
    if audit and "numericValue" in audit:
        return audit["numericValue"]
    return None


def _audit_value(audits: dict, key: str) -> float | None:
    audit = audits.get(key)
    if audit and "numericValue" in audit:
        return audit["numericValue"]
    return None
