"""Фейковые клиенты для тестов потребителей gsc — без сети и без ключей.

Повторяют публичные методы SearchConsole / PageSpeed / CrUX, данные задаются моделями:

    from gsc.testing import FakeSearchConsole
    sc = FakeSearchConsole(
        properties=[gsc.Property(site_url="sc-domain:example.com", permission_level="siteOwner")],
        rows=[gsc.Row(keys={"page": "https://example.com/"}, clicks=10, impressions=100, ctr=0.1, position=3.2)],
        inspections={"https://example.com/": gsc.Inspection(url="https://example.com/", property="sc-domain:example.com")},
        quota=1,  # после одной инспекции — QuotaExceeded
    )

Ошибку по конкретному URL задают исключением в словаре: inspections={url: gsc.ApiError("google", "boom")}.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Iterator, Sequence

from .core.errors import ApiError, PropertyNotFound, QuotaExceeded
from .core.models import (
    CruxHistory,
    CruxRecord,
    Inspection,
    InspectionError,
    PageSpeedError,
    PageSpeedResult,
    Property,
    Row,
    Sitemap,
)
from .core.pagespeed import CATEGORIES
from .core.search_console import SearchAnalyticsRows, property_for


class FakeSearchConsole:
    def __init__(
        self,
        *,
        properties: Iterable[Property] = (),
        rows: Iterable[Row] = (),
        inspections: dict[str, Inspection | Exception] | None = None,
        sitemaps: Iterable[Sitemap] = (),
        quota: int = 2000,
        first_incomplete_date: str | None = None,
    ) -> None:
        self.first_incomplete_date = first_incomplete_date
        self.properties = list(properties)
        self.rows = list(rows)
        self.inspections = inspections or {}
        self.sitemaps = list(sitemaps)
        self.quota = quota
        self.calls: list[tuple[str, tuple]] = []  # (метод, аргументы) — для проверок в тестах
        self.submitted: list[tuple[str, str]] = []

    def _require(self, site_url: str) -> None:
        if all(p.site_url != site_url for p in self.properties):
            raise PropertyNotFound(site_url)

    def list_properties(self) -> list[Property]:
        self.calls.append(("list_properties", ()))
        return list(self.properties)

    def get_property(self, site_url: str) -> Property:
        self._require(site_url)
        return next(p for p in self.properties if p.site_url == site_url)

    def property_for(self, url: str) -> str | None:
        return property_for(url, self.properties)

    def iter_search_analytics(
        self,
        property: str,
        start: dt.date | str | None = None,
        end: dt.date | str | None = None,
        dimensions: Sequence[str] = ("page",),
        search_type: str = "web",
        data_state: str = "final",
        filters: list[dict] | None = None,
        *,
        aggregation_type: str | None = None,
        by_day: bool = False,
        limit: int | None = None,
        page_size: int = 25_000,
    ) -> SearchAnalyticsRows:
        self._require(property)
        self.calls.append(
            ("iter_search_analytics", (property, start, end, tuple(dimensions), search_type, aggregation_type, by_day))
        )
        rows = SearchAnalyticsRows(iter([{"firstIncompleteDate": self.first_incomplete_date}, *self.rows[:limit]]))
        return rows

    def quota_remaining(self, property: str) -> int:
        return self.quota

    def inspect_url(self, url: str, property: str, language: str | None = "ru") -> Inspection:
        self._require(property)
        if self.quota <= 0:
            raise QuotaExceeded("google", "дневная квота URL Inspection исчерпана", retry_after=3600.0, daily=True)
        self.quota -= 1
        result = self.inspections.get(url) or Inspection(url=url, property=property)
        if isinstance(result, Exception):
            raise result
        return result

    def inspect_many(
        self, urls: Iterable[str], property: str, *, limit: int | None = None, language: str | None = "ru"
    ) -> Iterator[Inspection | InspectionError]:
        self._require(property)
        for count, url in enumerate(urls):
            if limit is not None and count >= limit:
                return
            try:
                yield self.inspect_url(url, property, language)
            except QuotaExceeded:
                raise
            except ApiError as exc:
                yield InspectionError(url=url, code=exc.code, message=exc.message, status=exc.status)

    def list_sitemaps(self, property: str) -> list[Sitemap]:
        self._require(property)
        return list(self.sitemaps)

    def get_sitemap(self, property: str, feedpath: str) -> Sitemap:
        self._require(property)
        return next((s for s in self.sitemaps if s.path == feedpath), Sitemap(path=feedpath))

    def submit_sitemap(self, property: str, feedpath: str) -> None:
        self._require(property)
        self.submitted.append((property, feedpath))


class FakePageSpeed:
    def __init__(self, results: dict[str, PageSpeedResult | Exception] | None = None) -> None:
        self.results = results or {}
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []

    def analyze(
        self,
        url: str,
        strategy: str = "mobile",
        categories: Sequence[str] = CATEGORIES,
        *,
        locale: str | None = None,
        screenshots: bool = False,
    ) -> PageSpeedResult:
        self.calls.append((url, strategy, tuple(categories)))
        result = self.results.get(url) or PageSpeedResult(url=url, final_url=url, strategy=strategy)
        if isinstance(result, Exception):
            raise result
        return result

    def analyze_many(
        self,
        urls: Iterable[str],
        strategy: str = "mobile",
        categories: Sequence[str] = CATEGORIES,
        *,
        concurrency: int = 4,
        locale: str | None = None,
        screenshots: bool = False,
    ) -> Iterator[PageSpeedResult | PageSpeedError]:
        for url in urls:
            try:
                yield self.analyze(url, strategy, categories, locale=locale, screenshots=screenshots)
            except QuotaExceeded as exc:
                if exc.daily:
                    raise
                yield PageSpeedError(url=url, code=exc.code, message=exc.message, status=exc.status)
            except ApiError as exc:
                yield PageSpeedError(url=url, code=exc.code, message=exc.message, status=exc.status)


class FakeCrUX:
    """records / histories: ключ — URL или origin; нет ключа → None (у Google нет данных)."""

    def __init__(
        self,
        records: dict[str, CruxRecord | Exception] | None = None,
        histories: dict[str, CruxHistory | Exception] | None = None,
    ) -> None:
        self.records = records or {}
        self.histories = histories or {}
        self.calls: list[tuple[str, str, str | None]] = []

    @staticmethod
    def _pick(store: dict, key: str) -> CruxRecord | CruxHistory | None:
        result = store.get(key)
        if isinstance(result, Exception):
            raise result
        return result

    def record(
        self,
        url: str | None = None,
        *,
        origin: str | None = None,
        form_factor: str | None = None,
        metrics: Sequence[str] | None = None,
    ) -> CruxRecord | None:
        key = url or origin or ""
        self.calls.append(("record", key, form_factor))
        result = self._pick(self.records, key)
        return result if isinstance(result, CruxRecord) or result is None else None

    def history(
        self,
        url: str | None = None,
        *,
        origin: str | None = None,
        form_factor: str | None = None,
        metrics: Sequence[str] | None = None,
        periods: int = 25,
    ) -> CruxHistory | None:
        key = url or origin or ""
        self.calls.append(("history", key, form_factor))
        result = self._pick(self.histories, key)
        return result if isinstance(result, CruxHistory) or result is None else None
