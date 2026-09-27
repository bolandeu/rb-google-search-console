"""Тесты клиента GSC — мокаем Google API, сеть не используется."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rb_gsc.core.client import GSCClient
from rb_gsc.core.models import SearchAnalyticsParams


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_client() -> GSCClient:
    """Создать GSCClient с замоканными сервисами (без реальной авторизации)."""
    client = GSCClient.__new__(GSCClient)
    client._sc = MagicMock()
    client._wm = MagicMock()
    return client


# ── Sites ────────────────────────────────────────────────────────────────────


class TestListSites:
    def test_returns_sites(self):
        client = _make_client()
        client._wm.sites().list().execute.return_value = {
            "siteEntry": [
                {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
                {"siteUrl": "https://test.com/", "permissionLevel": "siteFullUser"},
            ]
        }
        sites = client.list_sites()
        assert len(sites) == 2
        assert sites[0].site_url == "sc-domain:example.com"
        assert sites[1].permission_level == "siteFullUser"

    def test_empty_list(self):
        client = _make_client()
        client._wm.sites().list().execute.return_value = {"siteEntry": []}
        sites = client.list_sites()
        assert sites == []


# ── Search Analytics ─────────────────────────────────────────────────────────


class TestSearchAnalytics:
    def test_returns_rows(self):
        client = _make_client()
        client._wm.searchanalytics().query().execute.return_value = {
            "rows": [
                {"keys": ["keyword1"], "clicks": 100, "impressions": 1000, "ctr": 0.1, "position": 3.5},
                {"keys": ["keyword2"], "clicks": 50, "impressions": 500, "ctr": 0.1, "position": 7.0},
            ],
            "responseAggregationType": "auto",
        }
        result = client.search_analytics(SearchAnalyticsParams(
            site_url="sc-domain:example.com",
            start_date="2024-01-01",
            end_date="2024-01-31",
            dimensions=["query"],
        ))
        assert len(result.rows) == 2
        assert result.rows[0].keys == ["keyword1"]
        assert result.rows[0].clicks == 100
        assert result.rows[1].position == 7.0

    def test_empty_rows(self):
        client = _make_client()
        client._wm.searchanalytics().query().execute.return_value = {"rows": []}
        result = client.search_analytics(SearchAnalyticsParams(
            site_url="x", start_date="2024-01-01", end_date="2024-01-31",
        ))
        assert result.rows == []

    def test_query_body_passed(self):
        client = _make_client()
        mock_query = client._wm.searchanalytics().query
        mock_query().execute.return_value = {"rows": []}

        client.search_analytics(SearchAnalyticsParams(
            site_url="sc-domain:example.com",
            start_date="2024-01-01",
            end_date="2024-01-31",
            dimensions=["query", "page"],
            search_type="image",
            row_limit=500,
        ))

        call_kwargs = mock_query.call_args[1]
        assert call_kwargs["siteUrl"] == "sc-domain:example.com"
        body = call_kwargs["body"]
        assert body["startDate"] == "2024-01-01"
        assert body["dimensions"] == ["query", "page"]
        assert body["type"] == "image"
        assert body["rowLimit"] == 500


# ── URL Inspection ───────────────────────────────────────────────────────────


class TestInspectUrl:
    def test_returns_result(self):
        client = _make_client()
        client._sc.urlInspection().index().inspect().execute.return_value = {
            "inspectionResult": {
                "inspectionResultLink": "https://search.google.com/...",
                "indexStatusResult": {
                    "verdict": "PASS",
                    "coverageState": "Submitted and indexed",
                    "robotsTxtState": "ALLOWED",
                    "indexingState": "INDEXING_ALLOWED",
                    "lastCrawlTime": "2024-01-15T10:00:00Z",
                    "pageFetchState": "SUCCESSFUL",
                    "crawledAs": "DESKTOP",
                    "referringUrls": ["https://other.com/link"],
                },
            }
        }
        result = client.inspect_url("https://example.com/page", "sc-domain:example.com")
        assert result.verdict == "PASS"
        assert result.coverage_state == "Submitted and indexed"
        assert result.last_crawl_time == "2024-01-15T10:00:00Z"
        assert len(result.referring_urls) == 1


# ── Sitemaps ─────────────────────────────────────────────────────────────────


class TestSitemaps:
    def test_list_sitemaps(self):
        client = _make_client()
        client._wm.sitemaps().list().execute.return_value = {
            "sitemap": [
                {"path": "https://example.com/sitemap.xml", "type": "sitemap", "errors": 0, "warnings": 0},
                {"path": "https://example.com/sitemap-posts.xml", "type": "sitemap", "errors": 1, "warnings": 2},
            ]
        }
        sitemaps = client.list_sitemaps("sc-domain:example.com")
        assert len(sitemaps) == 2
        assert sitemaps[0].path == "https://example.com/sitemap.xml"
        assert sitemaps[1].errors == 1

    def test_empty_sitemaps(self):
        client = _make_client()
        client._wm.sitemaps().list().execute.return_value = {"sitemap": []}
        sitemaps = client.list_sitemaps("sc-domain:example.com")
        assert sitemaps == []


# ── PageSpeed ────────────────────────────────────────────────────────────────


class TestPageSpeed:
    def test_parse_response(self):
        from rb_gsc.core.pagespeed import PageSpeedClient

        client = PageSpeedClient.__new__(PageSpeedClient)
        client._api_key = ""

        data = {
            "lighthouseResult": {
                "requestedUrl": "https://example.com",
                "finalUrl": "https://example.com/",
                "lighthouseVersion": "12.0",
                "fetchTime": "2024-01-01T00:00:00Z",
                "categories": {
                    "performance": {"title": "Performance", "score": 0.85},
                    "seo": {"title": "SEO", "score": 0.92},
                },
                "audits": {
                    "first-contentful-paint": {"numericValue": 1200},
                    "largest-contentful-paint": {"numericValue": 2500},
                    "total-blocking-time": {"numericValue": 150},
                    "cumulative-layout-shift": {"numericValue": 0.05},
                    "speed-index": {"numericValue": 3000},
                    "interactive": {"numericValue": 4000},
                },
            }
        }
        result = client._parse_response(data, "mobile")
        assert result.url == "https://example.com/"
        assert result.overall_score == 0.85
        assert len(result.categories) == 2
        assert result.metrics.first_contentful_paint == 1200
        assert result.metrics.cumulative_layout_shift == 0.05
        assert result.lighthouse_version == "12.0"

    def test_parse_empty_audits(self):
        from rb_gsc.core.pagespeed import PageSpeedClient

        client = PageSpeedClient.__new__(PageSpeedClient)
        client._api_key = ""

        data = {
            "lighthouseResult": {
                "requestedUrl": "https://example.com",
                "finalUrl": "https://example.com/",
                "categories": {},
                "audits": {},
            }
        }
        result = client._parse_response(data, "desktop")
        assert result.categories == []
        assert result.metrics.first_contentful_paint is None
        assert result.overall_score is None
