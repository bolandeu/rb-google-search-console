from __future__ import annotations

from pathlib import Path

import pytest

import gsc
from gsc.core import services
from gsc.testing import FakePageSpeed, FakeSearchConsole

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
    assert "sitemap.xml" in invoke("sitemaps", "-s", SITE).stdout
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

    for real, fake in ((gsc.SearchConsole, FakeSearchConsole), (gsc.PageSpeed, FakePageSpeed)):
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
