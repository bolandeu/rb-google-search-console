"""Google Search Console API клиент."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

from loguru import logger

from .auth import credentials_from_service_account
from .models import (
    SearchAnalyticsParams,
    SearchAnalyticsResult,
    SearchAnalyticsRow,
    Site,
    Sitemap,
    UrlInspectionResult,
)


def _default_dates() -> tuple[str, str]:
    today = date.today()
    return (today - timedelta(days=30)).isoformat(), (today - timedelta(days=3)).isoformat()


class GSCClient:
    """Клиент Google Search Console API.

    Все методы sync — используют google-api-python-client (httplib2).
    """

    def __init__(
        self,
        service_account_path: str | Path | None = None,
        service_account_json: str | None = None,
        *,
        readonly: bool = True,
    ) -> None:
        from googleapiclient.discovery import build

        creds = credentials_from_service_account(
            path=service_account_path,
            json_str=service_account_json,
            readonly=readonly,
        )
        self._sc = build("searchconsole", "v1", credentials=creds)
        self._wm = build("webmasters", "v3", credentials=creds)

    # ── Sites ────────────────────────────────────────────────────────────────

    def list_sites(self) -> list[Site]:
        """Список всех сайтов пользователя."""
        resp = self._wm.sites().list().execute()
        entries = resp.get("siteEntry", [])
        return [
            Site(site_url=e["siteUrl"], permission_level=e.get("permissionLevel", ""))
            for e in entries
        ]

    def get_site(self, site_url: str) -> Site:
        """Информация о конкретном сайте."""
        resp = self._wm.sites().get(siteUrl=site_url).execute()
        return Site(site_url=resp["siteUrl"], permission_level=resp.get("permissionLevel", ""))

    def add_site(self, site_url: str) -> None:
        """Добавить сайт."""
        self._wm.sites().add(siteUrl=site_url).execute()
        logger.info(f"Сайт добавлен: {site_url}")

    def delete_site(self, site_url: str) -> None:
        """Удалить сайт."""
        self._wm.sites().delete(siteUrl=site_url).execute()
        logger.info(f"Сайт удалён: {site_url}")

    # ── Search Analytics ─────────────────────────────────────────────────────

    def search_analytics(self, params: SearchAnalyticsParams) -> SearchAnalyticsResult:
        """Данные поисковой аналитики."""
        body: dict = {
            "startDate": params.start_date,
            "endDate": params.end_date,
            "rowLimit": params.row_limit,
            "startRow": params.start_row,
            "type": params.search_type,
        }
        if params.dimensions:
            body["dimensions"] = params.dimensions
        if params.data_state:
            body["dataState"] = params.data_state
        if params.dimension_filter_groups:
            body["dimensionFilterGroups"] = params.dimension_filter_groups
        if params.aggregation_type:
            body["aggregationType"] = params.aggregation_type

        resp = self._wm.searchanalytics().query(
            siteUrl=params.site_url, body=body,
        ).execute()

        rows = [
            SearchAnalyticsRow(
                keys=r.get("keys", []),
                clicks=r.get("clicks", 0),
                impressions=r.get("impressions", 0),
                ctr=r.get("ctr", 0),
                position=r.get("position", 0),
            )
            for r in resp.get("rows", [])
        ]

        return SearchAnalyticsResult(
            rows=rows,
            response_aggregation_type=resp.get("responseAggregationType"),
        )

    def search_analytics_query(
        self,
        site_url: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        dimensions: list[str] | None = None,
        search_type: str = "web",
        row_limit: int = 1000,
        filters: list[dict] | None = None,
    ) -> SearchAnalyticsResult:
        """Упрощённый запрос поисковой аналитики."""
        d_from, d_to = _default_dates()
        dim_filter_groups = None
        if filters:
            dim_filter_groups = [{"filters": filters}]
        params = SearchAnalyticsParams(
            site_url=site_url,
            start_date=start_date or d_from,
            end_date=end_date or d_to,
            dimensions=dimensions,
            search_type=search_type,
            row_limit=row_limit,
            dimension_filter_groups=dim_filter_groups,
        )
        return self.search_analytics(params)

    # ── URL Inspection ───────────────────────────────────────────────────────

    def inspect_url(self, url: str, site_url: str) -> UrlInspectionResult:
        """Инспекция URL — статус индексации, покрытие, robots.txt."""
        body = {
            "inspectionUrl": url,
            "siteUrl": site_url,
        }
        resp = self._sc.urlInspection().index().inspect(body=body).execute()
        result = resp.get("inspectionResult", {})
        index_result = result.get("indexStatusResult", {})
        return UrlInspectionResult(
            inspection_result_link=result.get("inspectionResultLink", ""),
            index_status=index_result.get("verdict", ""),
            coverage_state=index_result.get("coverageState", ""),
            robots_txt_state=index_result.get("robotsTxtState", ""),
            indexing_state=index_result.get("indexingState", ""),
            last_crawl_time=index_result.get("lastCrawlTime", ""),
            page_fetch_state=index_result.get("pageFetchState", ""),
            crawled_as=index_result.get("crawledAs", ""),
            referring_urls=index_result.get("referringUrls", []),
            verdict=index_result.get("verdict", ""),
        )

    # ── Sitemaps ─────────────────────────────────────────────────────────────

    def list_sitemaps(self, site_url: str) -> list[Sitemap]:
        """Список карт сайта."""
        resp = self._wm.sitemaps().list(siteUrl=site_url).execute()
        return [
            Sitemap(
                path=s.get("path", ""),
                last_submitted=s.get("lastSubmitted"),
                is_pending=s.get("isPending", False),
                is_sitemaps_index=s.get("isSitemapsIndex", False),
                type=s.get("type"),
                last_downloaded=s.get("lastDownloaded"),
                warnings=s.get("warnings", 0),
                errors=s.get("errors", 0),
            )
            for s in resp.get("sitemap", [])
        ]

    def get_sitemap(self, site_url: str, feedpath: str) -> Sitemap:
        """Информация о конкретной карте сайта."""
        s = self._wm.sitemaps().get(siteUrl=site_url, feedpath=feedpath).execute()
        return Sitemap(
            path=s.get("path", ""),
            last_submitted=s.get("lastSubmitted"),
            is_pending=s.get("isPending", False),
            is_sitemaps_index=s.get("isSitemapsIndex", False),
            type=s.get("type"),
            last_downloaded=s.get("lastDownloaded"),
            warnings=s.get("warnings", 0),
            errors=s.get("errors", 0),
        )

    def submit_sitemap(self, site_url: str, feedpath: str) -> None:
        """Отправить карту сайта на индексацию."""
        self._wm.sitemaps().submit(siteUrl=site_url, feedpath=feedpath).execute()
        logger.info(f"Sitemap отправлена: {feedpath}")

    def delete_sitemap(self, site_url: str, feedpath: str) -> None:
        """Удалить карту сайта."""
        self._wm.sitemaps().delete(siteUrl=site_url, feedpath=feedpath).execute()
        logger.info(f"Sitemap удалена: {feedpath}")
