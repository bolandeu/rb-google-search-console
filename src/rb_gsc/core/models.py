"""Pydantic-модели для Google Search Console и PageSpeed Insights."""

from __future__ import annotations

from pydantic import BaseModel


# ── Search Console ───────────────────────────────────────────────────────────


class Site(BaseModel):
    site_url: str
    permission_level: str


class SearchAnalyticsParams(BaseModel):
    site_url: str
    start_date: str                          # YYYY-MM-DD
    end_date: str                            # YYYY-MM-DD
    dimensions: list[str] | None = None      # query, page, device, country, date, searchAppearance
    search_type: str = "web"                 # web, image, video, news, discover, googleNews
    row_limit: int = 1000                    # max 25000
    start_row: int = 0
    data_state: str | None = None            # all, final
    dimension_filter_groups: list[dict] | None = None
    aggregation_type: str | None = None      # auto, byPage, byProperty


class SearchAnalyticsRow(BaseModel):
    keys: list[str] = []
    clicks: float = 0.0
    impressions: float = 0.0
    ctr: float = 0.0
    position: float = 0.0


class SearchAnalyticsResult(BaseModel):
    rows: list[SearchAnalyticsRow]
    response_aggregation_type: str | None = None


class UrlInspectionResult(BaseModel):
    inspection_result_link: str = ""
    index_status: str = ""
    coverage_state: str = ""
    robots_txt_state: str = ""
    indexing_state: str = ""
    last_crawl_time: str = ""
    page_fetch_state: str = ""
    crawled_as: str = ""
    referring_urls: list[str] = []
    verdict: str = ""


class Sitemap(BaseModel):
    path: str
    last_submitted: str | None = None
    is_pending: bool = False
    is_sitemaps_index: bool = False
    type: str | None = None
    last_downloaded: str | None = None
    warnings: int = 0
    errors: int = 0


# ── PageSpeed Insights ───────────────────────────────────────────────────────


class PageSpeedParams(BaseModel):
    url: str
    strategy: str = "mobile"                 # desktop, mobile
    categories: list[str] | None = None      # performance, accessibility, best-practices, seo
    locale: str | None = None


class PageSpeedMetrics(BaseModel):
    first_contentful_paint: float | None = None
    largest_contentful_paint: float | None = None
    total_blocking_time: float | None = None
    cumulative_layout_shift: float | None = None
    speed_index: float | None = None
    interactive: float | None = None


class PageSpeedCategory(BaseModel):
    id: str
    title: str
    score: float | None = None


class PageSpeedResult(BaseModel):
    url: str
    strategy: str
    categories: list[PageSpeedCategory]
    metrics: PageSpeedMetrics
    overall_score: float | None = None
    lighthouse_version: str = ""
    fetch_time: str = ""
