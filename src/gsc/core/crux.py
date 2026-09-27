"""Chrome UX Report API: данные реальных посетителей Chrome — за 28 дней и история по неделям."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from ..providers.google import CruxProvider
from .errors import InvalidArguments
from .models import CruxApiMetric, CruxHistory, CruxHistoryMetric, CruxPeriod, CruxRecord
from .quota import RateLimiter

FORM_FACTORS = ("PHONE", "DESKTOP", "TABLET")
CRUX_PER_MINUTE = 150  # квота CrUX API на проект Google Cloud
HISTORY_MAX_PERIODS = 40


def _number(value: Any) -> float | None:
    """p75 приходит числом или строкой ("0.05" у CLS, "NaN" — нет данных за период)."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number  # NaN → None


def _date(raw: dict) -> str:
    return f"{raw['year']:04d}-{raw['month']:02d}-{raw['day']:02d}"


def _period(raw: dict) -> CruxPeriod:
    return CruxPeriod(first_date=_date(raw["firstDate"]), last_date=_date(raw["lastDate"]))


def _key_fields(key: dict) -> dict[str, Any]:
    return {"url": key.get("url"), "origin": key.get("origin"), "form_factor": key.get("formFactor")}


def parse_crux_record(response: dict) -> CruxRecord:
    """Ответ records:queryRecord → CruxRecord."""
    record = response.get("record", {})
    metrics: dict[str, CruxApiMetric] = {}
    for name, raw in record.get("metrics", {}).items():
        densities = [_number(b.get("density")) for b in raw.get("histogram", [])]
        good, needs_improvement, poor = densities if len(densities) == 3 else (None, None, None)
        metrics[name] = CruxApiMetric(
            p75=_number((raw.get("percentiles") or {}).get("p75")),
            good=good,
            needs_improvement=needs_improvement,
            poor=poor,
            fractions={k: v for k, v in (raw.get("fractions") or {}).items() if isinstance(v, int | float)},
        )
    period = record.get("collectionPeriod")
    normalized = (response.get("urlNormalizationDetails") or {}).get("normalizedUrl")
    return CruxRecord(
        **_key_fields(record.get("key", {})),
        period=_period(period) if period else None,
        metrics=metrics,
        normalized_url=normalized,
    )


def parse_crux_history(response: dict) -> CruxHistory:
    """Ответ records:queryHistoryRecord → CruxHistory (ряды по неделям, старые → новые)."""
    record = response.get("record", {})
    metrics: dict[str, CruxHistoryMetric] = {}
    for name, raw in record.get("metrics", {}).items():
        buckets = [[_number(d) for d in b.get("densities", [])] for b in raw.get("histogramTimeseries", [])]
        good, needs_improvement, poor = buckets if len(buckets) == 3 else ([], [], [])
        fractions = {
            k: [_number(x) for x in v.get("fractions", [])]
            for k, v in (raw.get("fractionTimeseries") or {}).items()
            if isinstance(v, dict)
        }
        metrics[name] = CruxHistoryMetric(
            p75=[_number(x) for x in (raw.get("percentilesTimeseries") or {}).get("p75s", [])],
            good=good,
            needs_improvement=needs_improvement,
            poor=poor,
            fractions=fractions,
        )
    return CruxHistory(
        **_key_fields(record.get("key", {})),
        periods=[_period(p) for p in record.get("collectionPeriods", [])],
        metrics=metrics,
    )


class CrUX:
    """Клиент Chrome UX Report API. Ключ — тот же, что у PageSpeed; создание без побочных эффектов.

    Данные есть только у URL и сайтов с заметным трафиком из Chrome: нет данных → None.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._api = CruxProvider(api_key=api_key, transport=transport)
        self._limiter = limiter or RateLimiter(CRUX_PER_MINUTE, 60.0)

    @staticmethod
    def _body(url: str | None, origin: str | None, form_factor: str | None, metrics: Sequence[str] | None) -> dict:
        if (url is None) == (origin is None):
            raise InvalidArguments("Нужен ровно один из url или origin.")
        body: dict[str, Any] = {"url": url} if url else {"origin": origin}
        if form_factor:
            if form_factor.upper() not in FORM_FACTORS:
                raise InvalidArguments(f"form_factor — {', '.join(FORM_FACTORS)} или None, а не '{form_factor}'.")
            body["formFactor"] = form_factor.upper()
        if metrics:
            body["metrics"] = list(metrics)
        return body

    def record(
        self,
        url: str | None = None,
        *,
        origin: str | None = None,
        form_factor: str | None = None,
        metrics: Sequence[str] | None = None,
    ) -> CruxRecord | None:
        """Последние 28 дней по URL или origin; form_factor — PHONE / DESKTOP / TABLET (None — все)."""
        body = self._body(url, origin, form_factor, metrics)
        self._limiter.acquire()
        response = self._api.query("queryRecord", body)
        return parse_crux_record(response) if response else None

    def history(
        self,
        url: str | None = None,
        *,
        origin: str | None = None,
        form_factor: str | None = None,
        metrics: Sequence[str] | None = None,
        periods: int = 25,
    ) -> CruxHistory | None:
        """История по неделям (каждая точка — окно 28 дней), по умолчанию 25 недель, максимум 40."""
        if not 1 <= periods <= HISTORY_MAX_PERIODS:
            raise InvalidArguments(f"periods — от 1 до {HISTORY_MAX_PERIODS}.")
        body = {**self._body(url, origin, form_factor, metrics), "collectionPeriodCount": periods}
        self._limiter.acquire()
        response = self._api.query("queryHistoryRecord", body)
        return parse_crux_history(response) if response else None
