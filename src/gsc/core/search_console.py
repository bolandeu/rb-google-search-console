"""Search Console: ресурсы, поисковая аналитика, URL Inspection, карты сайта."""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..providers.google import AccessDenied, SearchConsoleProvider, seconds_until_quota_reset
from .errors import ApiError, InvalidArguments, QuotaExceeded
from .models import Inspection, InspectionError, Issue, Property, RichResult, RichResultItem, Row, Sitemap
from .quota import INSPECTION_PER_MINUTE, InspectionQuota, RateLimiter

log = logging.getLogger(__name__)

DATA_DELAY_DAYS = 3  # данные Search Console появляются с задержкой 2–3 дня
DEFAULT_RANGE_DAYS = 28
PAGE_SIZE = 25_000  # максимум rowLimit в API


def default_range(today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    """Последние 28 дней, заканчивая 3 днями раньше сегодняшнего (задержка данных)."""
    end = (today or dt.date.today()) - dt.timedelta(days=DATA_DELAY_DAYS)
    return end - dt.timedelta(days=DEFAULT_RANGE_DAYS - 1), end


def property_for(url: str, properties: Iterable[Property]) -> str | None:
    """Какой ресурс покрывает URL: доменный предпочтительнее, среди URL-prefix — самый длинный.

    Доменный sc-domain:example.com покрывает example.com и все поддомены с любой
    схемой. Ресурсы с правом siteUnverifiedUser не считаются — данных по ним нет.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host:
        return None
    domains: list[str] = []
    prefixes: list[str] = []
    for prop in properties:
        if prop.permission_level == "siteUnverifiedUser":
            continue
        if prop.kind == "domain":
            domain = prop.site_url.removeprefix("sc-domain:").lower()
            if host == domain or host.endswith("." + domain):
                domains.append(prop.site_url)
        elif _prefix_covers(prop.site_url, parts):
            prefixes.append(prop.site_url)
    if domains:
        return max(domains, key=len)
    if prefixes:
        return max(prefixes, key=len)
    return None


def _prefix_covers(prefix: str, url: Any) -> bool:
    p = urlsplit(prefix)
    return (
        p.scheme.lower() == url.scheme.lower()
        and (p.hostname or "").lower() == (url.hostname or "").lower()
        and p.port == url.port
        and (url.path or "/").startswith(p.path or "/")
    )


def _date(value: dt.date | str) -> str:
    return value.isoformat() if isinstance(value, dt.date) else value


def _issues(raw: list[dict], message_key: str = "issueMessage") -> list[Issue]:
    return [
        Issue(message=i.get(message_key, ""), severity=i.get("severity", ""), type=i.get("issueType"))
        for i in raw or []
    ]


def parse_inspection(url: str, site_url: str, response: dict) -> Inspection:
    """Ответ index:inspect → Inspection (исходный inspectionResult — в raw)."""
    result = response.get("inspectionResult", {})
    index = result.get("indexStatusResult", {})
    mobile = result.get("mobileUsabilityResult", {})
    amp = result.get("ampResult", {})
    rich = result.get("richResultsResult", {})
    return Inspection(
        url=url,
        property=site_url,
        inspection_result_link=result.get("inspectionResultLink", ""),
        verdict=index.get("verdict", ""),
        coverage_state=index.get("coverageState", ""),
        indexing_state=index.get("indexingState", ""),
        robots_txt_state=index.get("robotsTxtState", ""),
        page_fetch_state=index.get("pageFetchState", ""),
        last_crawl_time=index.get("lastCrawlTime", ""),
        crawled_as=index.get("crawledAs", ""),
        google_canonical=index.get("googleCanonical", ""),
        user_canonical=index.get("userCanonical", ""),
        sitemaps=index.get("sitemap", []),
        referring_urls=index.get("referringUrls", []),
        mobile_verdict=mobile.get("verdict", ""),
        mobile_issues=_issues(mobile.get("issues", []), "message"),
        amp_verdict=amp.get("verdict", ""),
        amp_issues=_issues(amp.get("issues", [])),
        rich_results_verdict=rich.get("verdict", ""),
        rich_results=[
            RichResult(
                type=d.get("richResultType", ""),
                items=[
                    RichResultItem(name=i.get("name", ""), issues=_issues(i.get("issues", [])))
                    for i in d.get("items", [])
                ],
            )
            for d in rich.get("detectedItems", [])
        ],
        raw=result,
    )


def _sitemap(raw: dict) -> Sitemap:
    return Sitemap(
        path=raw.get("path", ""),
        last_submitted=raw.get("lastSubmitted"),
        is_pending=raw.get("isPending", False),
        is_sitemaps_index=raw.get("isSitemapsIndex", False),
        type=raw.get("type"),
        last_downloaded=raw.get("lastDownloaded"),
        warnings=int(raw.get("warnings", 0)),
        errors=int(raw.get("errors", 0)),
    )


class SearchConsole:
    """Клиент Search Console. Создание ничего не делает: ключ читается и токен берётся при первом запросе.

    Учётные данные — из `gsc auth login` / переменных окружения (см. gsc.core.auth);
    их нет → NotAuthorized с командой-исправлением.
    """

    def __init__(
        self,
        *,
        quota: InspectionQuota | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._api = SearchConsoleProvider(transport=transport)
        self._write_api: SearchConsoleProvider | None = None
        self.quota = quota or InspectionQuota()
        self._sleep = sleep
        self._limiters: dict[str, RateLimiter] = {}

    # --- ресурсы -------------------------------------------------------------------

    def list_properties(self) -> list[Property]:
        entries = self._api.list_sites().get("siteEntry", [])
        return [Property(site_url=e["siteUrl"], permission_level=e.get("permissionLevel", "")) for e in entries]

    def get_property(self, site_url: str) -> Property:
        """Ресурс по точному site_url; нет доступа → PropertyNotFound."""
        raw = self._api.get_site(site_url)
        return Property(site_url=raw.get("siteUrl", site_url), permission_level=raw.get("permissionLevel", ""))

    def property_for(self, url: str) -> str | None:
        return property_for(url, self.list_properties())

    # --- поисковая аналитика --------------------------------------------------------

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
        page_size: int = PAGE_SIZE,
    ) -> Iterator[Row]:
        """Строки отчёта постранично (rowLimit + startRow): весь отчёт в памяти не держится.

        filters — dimensionFilters API как есть: [{"dimension": "page", "operator": "contains",
        "expression": "/blog/"}]. limit — сколько строк всего (None — все).
        """
        d_start, d_end = default_range()
        dims = list(dimensions)
        body: dict[str, Any] = {
            "startDate": _date(start or d_start),
            "endDate": _date(end or d_end),
            "dimensions": dims,
            "type": search_type,
            "dataState": data_state,
        }
        if filters:
            body["dimensionFilterGroups"] = [{"filters": filters}]
        start_row = 0
        yielded = 0
        while True:
            size = page_size if limit is None else min(page_size, limit - yielded)
            if size <= 0:
                return
            rows = self._api.search_analytics(property, {**body, "rowLimit": size, "startRow": start_row}).get(
                "rows", []
            )
            for raw in rows:
                yield Row(
                    keys=dict(zip(dims, raw.get("keys", []), strict=False)),
                    clicks=int(raw.get("clicks", 0)),
                    impressions=int(raw.get("impressions", 0)),
                    ctr=float(raw.get("ctr", 0.0)),
                    position=float(raw.get("position", 0.0)),
                )
            yielded += len(rows)
            if len(rows) < size:
                return
            start_row += len(rows)

    # --- URL Inspection --------------------------------------------------------------

    def quota_remaining(self, property: str) -> int:
        """Оценка оставшихся на сегодня инспекций по ресурсу (локальный учёт, см. InspectionQuota)."""
        return self.quota.remaining(property)

    def inspect_url(self, url: str, property: str, language: str | None = "ru") -> Inspection:
        """Одна инспекция. URL вне ресурса / нет доступа → PropertyNotFound; квота → QuotaExceeded."""
        try:
            return self._inspect(url, property, language)
        except AccessDenied as exc:
            from .errors import PropertyNotFound

            raise PropertyNotFound(property, exc.detail) from exc

    def _inspect(self, url: str, property: str, language: str | None) -> Inspection:
        if self.quota.remaining(property) <= 0:
            raise QuotaExceeded(
                self._api.name,
                f"дневная квота URL Inspection по ресурсу {property} исчерпана (учёт gsc)",
                retry_after=seconds_until_quota_reset(),
                daily=True,
            )
        limiter = self._limiters.setdefault(property, RateLimiter(INSPECTION_PER_MINUTE, 60.0, sleep=self._sleep))
        for attempt in range(3):
            limiter.acquire()
            try:
                response = self._api.inspect(url, property, language)
            except QuotaExceeded as exc:
                if exc.daily:
                    self.quota.mark_exhausted(property)
                    raise
                if attempt == 2:
                    raise
                log.debug("minute quota hit for %s, sleeping %.0fs", property, exc.retry_after or 60)
                self._sleep(exc.retry_after or 60.0)
                continue
            self.quota.record(property)
            return parse_inspection(url, property, response)
        raise AssertionError("unreachable")  # pragma: no cover

    def inspect_many(
        self, urls: Iterable[str], property: str, *, limit: int | None = None, language: str | None = "ru"
    ) -> Iterator[Inspection | InspectionError]:
        """Инспекция списка URL с соблюдением темпа (600/мин на ресурс).

        Ошибка по отдельному URL выдаётся как InspectionError, обход продолжается.
        Дневная квота → QuotaExceeded из итератора; всё выданное до этого уже у
        вызывающего. Доступ к ресурсу проверяется одним запросом до начала
        (PropertyNotFound), limit — сколько URL инспектировать максимум.
        """
        self.get_property(property)
        for count, url in enumerate(urls):
            if limit is not None and count >= limit:
                return
            try:
                yield self._inspect(url, property, language)
            except QuotaExceeded:
                raise
            except ApiError as exc:
                yield InspectionError(url=url, code=exc.code, message=exc.message, status=exc.status)

    # --- карты сайта -------------------------------------------------------------------

    def list_sitemaps(self, property: str) -> list[Sitemap]:
        return [_sitemap(s) for s in self._api.list_sitemaps(property).get("sitemap", [])]

    def get_sitemap(self, property: str, feedpath: str) -> Sitemap:
        return _sitemap(self._api.get_sitemap(property, feedpath))

    def submit_sitemap(self, property: str, feedpath: str) -> None:
        """Отправить карту сайта (нужен полный scope webmasters — отдельный токен)."""
        if not feedpath.startswith(("http://", "https://")):
            raise InvalidArguments(f"Карта сайта — полный URL, а не '{feedpath}'.")
        if self._write_api is None:
            self._write_api = SearchConsoleProvider(readonly=False, transport=self._transport)
        self._write_api.submit_sitemap(property, feedpath)
