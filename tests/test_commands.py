from __future__ import annotations

from pathlib import Path

import pytest

import gsc
from gsc.core import services
from gsc.testing import FakeCrUX, FakePageSpeed, FakeSearchConsole

from .test_cli import invoke, invoke_json

SITE = "sc-domain:example.com"


@pytest.fixture
def sc(monkeypatch: pytest.MonkeyPatch) -> FakeSearchConsole:
    fake = FakeSearchConsole(
        properties=[
            gsc.Property(site_url=SITE, permission_level="siteOwner"),
            gsc.Property(site_url="https://shop.other.org/", permission_level="siteFullUser"),
        ],
        rows=[
            gsc.Row(
                keys={"query": "диван", "page": "https://example.com/"}, clicks=5, impressions=50, ctr=0.1, position=2
            )
        ]
        * 3,
        inspections={
            "https://example.com/a": gsc.Inspection(
                url="https://example.com/a",
                property=SITE,
                verdict="PASS",
                coverage_state="Submitted and indexed",
                sitemaps=["https://example.com/sitemap.xml"],
                referring_urls=["https://example.com/"],
                rich_results_verdict="PASS",
                rich_results=[gsc.RichResult(type="FAQ")],
                raw={"big": "blob"},
            ),
            "https://example.com/bad": gsc.ApiError("google", "boom", status=400),
        },
        sitemaps=[gsc.Sitemap(path="https://example.com/sitemap.xml", errors=1)],
    )
    monkeypatch.setattr(services, "search_console", lambda: fake)
    return fake


@pytest.fixture
def psi(monkeypatch: pytest.MonkeyPatch) -> FakePageSpeed:
    result = gsc.PageSpeedResult(
        url="https://example.com/",
        final_url="https://example.com/",
        strategy="mobile",
        lighthouse_version="12.2.1",
        scores={"performance": 0.45, "seo": 0.95, "accessibility": None},
        lab=gsc.LabMetrics(lcp_ms=3100, cls=0.12),
        crux_origin=gsc.Crux(
            lcp=gsc.CruxMetric(percentile=2500, value=2500, category="AVERAGE"),
            cls=gsc.CruxMetric(percentile=5, value=0.05, category="FAST"),
        ),
        crux_origin_fallback=True,
        audits=[
            gsc.Audit(id="render-blocking-resources", title="RBR", score=0.2, display_value="450 ms"),
            gsc.Audit(id="diagnostics", title="Diag", score=0.1, score_display_mode="informative"),
        ],
    )
    fake = FakePageSpeed(
        {"https://example.com/": result, "https://example.com/bad": gsc.ApiError("pagespeed", "lighthouse failed")}
    )
    monkeypatch.setattr(services, "pagespeed", lambda: fake)
    return fake


def test_sites(sc: FakeSearchConsole) -> None:
    code, payload = invoke_json("sites")
    assert code == 0 and payload["count"] == 2
    assert payload["sites"][0] == {"site_url": SITE, "permission_level": "siteOwner", "kind": "domain"}
    assert "sc-domain:example.com" in invoke("sites").stdout

    _, payload = invoke_json("sites", "--for", "https://blog.example.com/x")
    assert payload["site"] == SITE
    _, payload = invoke_json("sites", "--for", "https://nowhere.net/")
    assert payload["site"] is None
    assert "Ни один ресурс" in invoke("sites", "--for", "https://nowhere.net/").stdout


def test_site(sc: FakeSearchConsole) -> None:
    code, payload = invoke_json("site", "-s", SITE)
    assert code == 0 and payload["kind"] == "domain"
    code, payload = invoke_json("site", "-s", "sc-domain:nope.com")
    assert code == 2 and "Search Console" in payload["error"]["action"]
    assert "siteOwner" in invoke("site", "-s", SITE).stdout


def test_site_comes_from_project_config(sc: FakeSearchConsole, tmp_path: Path) -> None:
    code, payload = invoke_json("--project", str(tmp_path), "analytics")
    assert code == 2 and "-s" in payload["error"]["message"]
    assert invoke("--project", str(tmp_path), "init", "--site", SITE).exit_code == 0
    code, payload = invoke_json("--project", str(tmp_path), "analytics")
    assert code == 0 and payload["site"] == SITE
    _, payload = invoke_json("--project", str(tmp_path), "status")
    assert payload["site"] == SITE


def test_analytics(sc: FakeSearchConsole) -> None:
    code, payload = invoke_json("analytics", "-s", SITE, "-d", "query,page", "--limit", "2")
    assert code == 0
    assert payload["dimensions"] == ["query", "page"] and payload["count"] == 2
    assert payload["rows"][0]["keys"]["query"] == "диван"
    start, end = gsc.default_range()
    assert (payload["start_date"], payload["end_date"]) == (start.isoformat(), end.isoformat())
    assert sc.calls[-1][1][3] == ("query", "page")

    _, payload = invoke_json("analytics", "-s", SITE, "--limit", "0", "--start-date", "2026-01-01")
    assert payload["count"] == 3 and payload["start_date"] == "2026-01-01"
    human = invoke("analytics", "-s", SITE, "-d", "query,page")
    assert "диван" in human.stdout and "10.0%" in human.stdout


def test_inspect(sc: FakeSearchConsole) -> None:
    code, payload = invoke_json("inspect", "-s", SITE, "https://example.com/a", "https://example.com/bad")
    assert code == 0 and payload["count"] == 2
    first, second = payload["results"]
    assert first["verdict"] == "PASS" and "raw" not in first
    assert second == {
        "url": "https://example.com/bad",
        "code": "PROVIDER_ERROR",
        "message": "Provider 'google': boom",
        "status": 400,
    }
    assert payload["quota_exhausted"] is False and payload["quota_remaining"] == 1998

    _, payload = invoke_json("inspect", "-s", SITE, "https://example.com/a", "--raw")
    assert payload["results"][0]["raw"] == {"big": "blob"}

    human = invoke("inspect", "-s", SITE, "https://example.com/a", "https://example.com/bad")
    assert "Submitted and indexed" in human.stdout and "FAQ" in human.stdout
    assert "boom" in human.stderr


def test_inspect_keeps_partial_results_on_daily_quota(sc: FakeSearchConsole) -> None:
    sc.quota = 1
    code, payload = invoke_json("inspect", "-s", SITE, "https://example.com/a", "https://example.com/b")
    assert code == 0 and payload["count"] == 1 and payload["quota_exhausted"] is True
    sc.quota = 1
    assert "Остановлено" in invoke("inspect", "-s", SITE, "https://example.com/a", "https://example.com/b").stderr
    code, payload = invoke_json("inspect", "-s", SITE, "https://example.com/a")
    assert code == 5 and payload["error"]["daily"] is True


def test_sitemaps(sc: FakeSearchConsole) -> None:
    _, payload = invoke_json("sitemaps", "-s", SITE)
    assert payload["sitemaps"][0]["errors"] == 1
    assert "example.com" in invoke("sitemaps", "-s", SITE).stdout
    sc.sitemaps = []
    assert "Карт сайта нет" in invoke("sitemaps", "-s", SITE).stdout

    _, payload = invoke_json("sitemap", "-s", SITE, "https://example.com/s.xml")
    assert payload["path"] == "https://example.com/s.xml"
    assert "Загружена Google" in invoke("sitemap", "-s", SITE, "https://example.com/s.xml").stdout


def test_submit_sitemap_dry_run_then_real(sc: FakeSearchConsole) -> None:
    code, payload = invoke_json("submit-sitemap", "-s", SITE, "https://example.com/sitemap.xml", "--dry-run")
    assert code == 0 and payload["dry_run"] is True and payload["submitted"] is False
    assert sc.submitted == []
    assert "Будет отправлена" in invoke("--dry-run", "submit-sitemap", "-s", SITE, "https://example.com/s.xml").stdout

    code, payload = invoke_json("submit-sitemap", "-s", SITE, "https://example.com/sitemap.xml")
    assert code == 0 and payload["submitted"] is True
    assert sc.submitted == [(SITE, "https://example.com/sitemap.xml")]


def test_pagespeed(psi: FakePageSpeed) -> None:
    code, payload = invoke_json("pagespeed", "https://example.com/", "-c", "performance,seo", "--strategy", "desktop")
    assert code == 0 and payload["results"][0]["lighthouse_version"] == "12.2.1"
    assert psi.calls[-1] == ("https://example.com/", "desktop", ("performance", "seo"))

    _, payload = invoke_json("pagespeed", "https://example.com/", "https://example.com/bad")
    assert payload["count"] == 2 and payload["results"][1]["code"] == "PROVIDER_ERROR"

    human = invoke("pagespeed", "https://example.com/", "https://example.com/bad", "--audits")
    assert "performance: 45" in human.stdout and "LCP 3100 мс" in human.stdout
    assert "по URL данных нет" in human.stdout and "CLS 0.05" in human.stdout
    assert "render-blocking-resources" in human.stdout and "diagnostics" not in human.stdout
    assert "lighthouse failed" in human.stderr

    code, _ = invoke_json("pagespeed", "https://example.com/", "--concurrency", "0")
    assert code == 2


def test_fakes_mirror_real_api() -> None:
    """Фейки должны оставаться совместимыми с настоящими клиентами по публичным методам."""
    import inspect

    for real, fake in ((gsc.SearchConsole, FakeSearchConsole), (gsc.PageSpeed, FakePageSpeed), (gsc.CrUX, FakeCrUX)):
        public = {n for n in dir(real) if not n.startswith("_") and callable(getattr(real, n))}
        for name in public:
            assert hasattr(fake, name), f"{fake.__name__} нет {name}"
            real_params = list(inspect.signature(getattr(real, name)).parameters)
            fake_params = list(inspect.signature(getattr(fake, name)).parameters)
            assert real_params == fake_params, name


def test_fake_search_console_extras() -> None:
    fake = FakeSearchConsole(properties=[gsc.Property(site_url=SITE)])
    assert fake.property_for("https://example.com/") == SITE
    assert fake.get_property(SITE).site_url == SITE
    assert fake.list_properties()[0].site_url == SITE
    assert fake.inspect_url("https://example.com/z", SITE).url == "https://example.com/z"
    assert list(fake.inspect_many(["a", "b", "c"], SITE, limit=2))[-1].url == "b"
    with pytest.raises(gsc.PropertyNotFound):
        list(fake.iter_search_analytics("sc-domain:nope.com"))
    quota_hit = FakePageSpeed({"u": gsc.QuotaExceeded("pagespeed", "minute", retry_after=60, daily=False)})
    assert isinstance(next(quota_hit.analyze_many(["u"])), gsc.PageSpeedError)
    daily = FakePageSpeed({"u": gsc.QuotaExceeded("pagespeed", "day", retry_after=60, daily=True)})
    with pytest.raises(gsc.QuotaExceeded):
        next(daily.analyze_many(["u"]))


@pytest.fixture
def cx(monkeypatch: pytest.MonkeyPatch) -> FakeCrUX:
    record = gsc.CruxRecord(
        origin="https://example.com",
        period=gsc.CruxPeriod(first_date="2026-08-29", last_date="2026-09-25"),
        metrics={
            "round_trip_time": gsc.CruxApiMetric(p75=157),
            "cumulative_layout_shift": gsc.CruxApiMetric(p75=0.05, good=0.97, needs_improvement=0.02, poor=0.01),
            "largest_contentful_paint": gsc.CruxApiMetric(p75=1884, good=0.88, needs_improvement=0.09, poor=0.03),
            "form_factors": gsc.CruxApiMetric(fractions={"phone": 0.52, "desktop": 0.48}),
        },
    )
    history = gsc.CruxHistory(
        origin="https://example.com",
        form_factor="PHONE",
        periods=[
            gsc.CruxPeriod(first_date="2026-03-08", last_date="2026-04-04"),
            gsc.CruxPeriod(first_date="2026-08-23", last_date="2026-09-19"),
        ],
        metrics={
            "largest_contentful_paint": gsc.CruxHistoryMetric(p75=[1708, 2009], good=[0.9, 0.85]),
            "navigation_types": gsc.CruxHistoryMetric(fractions={"navigate": [0.8, 0.7]}),
        },
    )
    fake = FakeCrUX(
        records={"https://example.com": record, "https://example.com/boom": gsc.ApiError("crux", "boom")},
        histories={"https://example.com": history, "https://example.com/empty": gsc.CruxHistory()},
    )
    monkeypatch.setattr(services, "crux", lambda: fake)
    return fake


def test_crux_record(cx: FakeCrUX) -> None:
    code, payload = invoke_json("crux", "--origin", "https://example.com", "--form-factor", "phone")
    assert code == 0 and payload["record"]["metrics"]["largest_contentful_paint"]["good"] == 0.88
    assert cx.calls[-1] == ("record", "https://example.com", "phone")
    human = invoke("crux", "--origin", "https://example.com").stdout
    assert "1884 мс" in human and "88%" in human and "0.05" in human and "phone 52%" in human
    assert human.index("largest_contentful_paint") < human.index("round_trip_time")  # основные метрики первыми

    code, payload = invoke_json("crux", "https://example.com/rare")
    assert code == 0 and payload["record"] is None
    assert "нет данных" in invoke("crux", "https://example.com/rare").stdout
    code, payload = invoke_json("crux", "https://example.com/boom")
    assert code == 5


def test_crux_history(cx: FakeCrUX) -> None:
    code, payload = invoke_json("crux", "--origin", "https://example.com", "--history")
    assert code == 0 and payload["history"]["metrics"]["largest_contentful_paint"]["p75"] == [1708, 2009]
    human = invoke("crux", "--origin", "https://example.com", "--history").stdout
    assert "1708 мс" in human and "2009 мс" in human and "85%" in human
    assert "Нет периодов" in invoke("crux", "--origin", "https://example.com/empty", "--history").stdout
    assert "нет данных" in invoke("crux", "https://nope.com/", "--history").stdout


def test_crux_needs_exactly_one_target(cx: FakeCrUX) -> None:
    assert invoke_json("crux")[0] == 2
    assert invoke_json("crux", "https://a.com/", "--origin", "https://a.com")[0] == 2


def test_analytics_filters_aggregation_by_day(sc: FakeSearchConsole) -> None:
    sc.first_incomplete_date = "2026-09-26"
    code, payload = invoke_json(
        "analytics", "-s", SITE, "-f", "page:contains:https://example.com/blog/", "--aggregation", "byPage", "--by-day"
    )
    assert code == 0 and payload["first_incomplete_date"] == "2026-09-26"
    assert sc.calls[-1][1][5:] == ("byPage", True)
    code, payload = invoke_json("analytics", "-s", SITE, "-f", "page:like:x")
    assert code == 2 and "equals" in payload["error"]["message"]
    assert invoke_json("analytics", "-s", SITE, "-f", "page")[0] == 2


def test_parse_filter_keeps_colons_in_expression() -> None:
    assert services.parse_filter("page:equals:https://example.com/a") == {
        "dimension": "page",
        "operator": "equals",
        "expression": "https://example.com/a",
    }


def test_pagespeed_warnings_and_distribution(psi: FakePageSpeed) -> None:
    result = psi.results["https://example.com/"]
    assert isinstance(result, gsc.PageSpeedResult)
    result.runtime_error = "FAILED_DOCUMENT_REQUEST: timeout"
    result.run_warnings = ["redirected"]
    assert result.crux_origin is not None and result.crux_origin.lcp is not None
    result.crux_origin.lcp.good = 0.8
    human = invoke("pagespeed", "https://example.com/")
    assert "FAILED_DOCUMENT_REQUEST" in human.stderr and "redirected" in human.stderr
    assert "хороших 80%" in human.stdout
    invoke_json("pagespeed", "https://example.com/", "--screenshots")
    assert psi.calls[-1][2] == ("performance", "accessibility", "best-practices", "seo")


def test_sitemap_contents_in_output(sc: FakeSearchConsole) -> None:
    sc.sitemaps = [
        gsc.Sitemap(path="https://example.com/s.xml", contents=[gsc.SitemapContent(type="web", submitted=120)])
    ]
    _, payload = invoke_json("sitemaps", "-s", SITE)
    assert payload["sitemaps"][0]["contents"] == [{"type": "web", "submitted": 120, "indexed": None}]
    assert "web: 120" in invoke("sitemaps", "-s", SITE).stdout
    assert "URL (web)" in invoke("sitemap", "-s", SITE, "https://example.com/s.xml").stdout


def test_fake_crux_raises_configured_error() -> None:
    fake = FakeCrUX(histories={"x": gsc.ApiError("crux", "boom")})
    with pytest.raises(gsc.ApiError):
        fake.history("x")
