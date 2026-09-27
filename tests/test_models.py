"""Тесты моделей данных — без сетевых запросов."""

from __future__ import annotations

from rb_gsc.core.models import (
    PageSpeedCategory,
    PageSpeedMetrics,
    PageSpeedParams,
    PageSpeedResult,
    SearchAnalyticsParams,
    SearchAnalyticsResult,
    SearchAnalyticsRow,
    Site,
    Sitemap,
    UrlInspectionResult,
)


class TestSite:
    def test_basic(self):
        s = Site(site_url="sc-domain:example.com", permission_level="siteOwner")
        assert s.site_url == "sc-domain:example.com"
        assert s.permission_level == "siteOwner"


class TestSearchAnalyticsParams:
    def test_required(self):
        p = SearchAnalyticsParams(site_url="sc-domain:example.com", start_date="2024-01-01", end_date="2024-01-31")
        assert p.site_url == "sc-domain:example.com"
        assert p.row_limit == 1000

    def test_defaults(self):
        p = SearchAnalyticsParams(site_url="x", start_date="2024-01-01", end_date="2024-01-31")
        assert p.dimensions is None
        assert p.search_type == "web"
        assert p.start_row == 0
        assert p.data_state is None
        assert p.aggregation_type is None

    def test_all_fields(self):
        p = SearchAnalyticsParams(
            site_url="x", start_date="2024-01-01", end_date="2024-01-31",
            dimensions=["query", "page"], search_type="image",
            row_limit=500, start_row=100, data_state="final",
            aggregation_type="byPage",
        )
        assert p.dimensions == ["query", "page"]
        assert p.row_limit == 500


class TestSearchAnalyticsRow:
    def test_basic(self):
        row = SearchAnalyticsRow(keys=["keyword"], clicks=100, impressions=1000, ctr=0.1, position=5.5)
        assert row.keys == ["keyword"]
        assert row.clicks == 100
        assert row.ctr == 0.1

    def test_defaults(self):
        row = SearchAnalyticsRow()
        assert row.keys == []
        assert row.clicks == 0.0


class TestSearchAnalyticsResult:
    def test_basic(self):
        rows = [SearchAnalyticsRow(keys=["q"], clicks=10, impressions=100, ctr=0.1, position=3.0)]
        r = SearchAnalyticsResult(rows=rows)
        assert len(r.rows) == 1
        assert r.response_aggregation_type is None


class TestUrlInspectionResult:
    def test_defaults(self):
        r = UrlInspectionResult()
        assert r.index_status == ""
        assert r.referring_urls == []

    def test_all_fields(self):
        r = UrlInspectionResult(
            verdict="PASS", index_status="PASS",
            coverage_state="Submitted and indexed",
            robots_txt_state="ALLOWED",
            last_crawl_time="2024-01-01T00:00:00Z",
        )
        assert r.verdict == "PASS"
        assert r.coverage_state == "Submitted and indexed"


class TestSitemap:
    def test_basic(self):
        s = Sitemap(path="https://example.com/sitemap.xml")
        assert s.path == "https://example.com/sitemap.xml"
        assert s.errors == 0
        assert s.warnings == 0

    def test_all_fields(self):
        s = Sitemap(
            path="https://example.com/sitemap.xml",
            last_submitted="2024-01-01", is_pending=False,
            is_sitemaps_index=True, type="sitemap",
            errors=1, warnings=2,
        )
        assert s.is_sitemaps_index is True
        assert s.errors == 1


class TestPageSpeedParams:
    def test_defaults(self):
        p = PageSpeedParams(url="https://example.com")
        assert p.strategy == "mobile"
        assert p.categories is None

    def test_all(self):
        p = PageSpeedParams(url="https://example.com", strategy="desktop", categories=["performance", "seo"], locale="ru")
        assert p.strategy == "desktop"
        assert len(p.categories) == 2


class TestPageSpeedMetrics:
    def test_defaults_none(self):
        m = PageSpeedMetrics()
        assert m.first_contentful_paint is None
        assert m.cumulative_layout_shift is None

    def test_values(self):
        m = PageSpeedMetrics(first_contentful_paint=1200, largest_contentful_paint=2500, cumulative_layout_shift=0.05)
        assert m.first_contentful_paint == 1200
        assert m.cumulative_layout_shift == 0.05


class TestPageSpeedResult:
    def test_basic(self):
        r = PageSpeedResult(
            url="https://example.com", strategy="mobile",
            categories=[PageSpeedCategory(id="performance", title="Performance", score=0.85)],
            metrics=PageSpeedMetrics(first_contentful_paint=1200),
            overall_score=0.85,
        )
        assert r.overall_score == 0.85
        assert r.categories[0].score == 0.85

    def test_model_dump_roundtrip(self):
        r = PageSpeedResult(
            url="https://example.com", strategy="desktop",
            categories=[], metrics=PageSpeedMetrics(),
        )
        d = r.model_dump()
        assert d["url"] == "https://example.com"
        assert d["strategy"] == "desktop"
