"""Фейковые клиенты для тестов потребителей gsc — без сети и без ключей.

Повторяют публичные методы SearchConsole / PageSpeed, данные задаются моделями:

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
    Inspection,
    InspectionError,
    PageSpeedError,
    PageSpeedResult,
    Property,
    Row,
    Sitemap,
)
from .core.search_console import property_for


class FakeSearchConsole:
    def __init__(
        self,
        *,
        properties: Iterable[Property] = (),
        rows: Iterable[Row] = (),
        inspections: dict[str, Inspection | Exception] | None = None,
        sitemaps: Iterable[Sitemap] = (),
        quota: int = 2000,
    ) -> None:
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
        limit: int | None = None,
        page_size: int = 25_000,
    ) -> Iterator[Row]:
        self._require(property)
        self.calls.append(("iter_search_analytics", (property, start, end, tuple(dimensions), search_type)))
        yield from self.rows[:limit]

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
        categories: Sequence[str] = ("performance",),
        *,
        locale: str | None = None,
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
        categories: Sequence[str] = ("performance",),
        *,
        concurrency: int = 4,
        locale: str | None = None,
    ) -> Iterator[PageSpeedResult | PageSpeedError]:
        for url in urls:
            try:
                yield self.analyze(url, strategy, categories, locale=locale)
            except QuotaExceeded as exc:
                if exc.daily:
                    raise
                yield PageSpeedError(url=url, code=exc.code, message=exc.message, status=exc.status)
            except ApiError as exc:
                yield PageSpeedError(url=url, code=exc.code, message=exc.message, status=exc.status)
