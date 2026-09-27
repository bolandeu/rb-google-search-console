from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest

import gsc
from gsc.core.quota import InspectionQuota, RateLimiter

from .conftest import google_error, json_response

pytestmark = pytest.mark.usefixtures("no_token_exchange")

INSPECT_RESPONSE = {
    "inspectionResult": {
        "inspectionResultLink": "https://search.google.com/search-console/inspect?id=1",
        "indexStatusResult": {
            "verdict": "PASS",
            "coverageState": "Submitted and indexed",
            "robotsTxtState": "ALLOWED",
            "indexingState": "INDEXING_ALLOWED",
            "lastCrawlTime": "2026-09-20T10:00:00Z",
            "pageFetchState": "SUCCESSFUL",
            "googleCanonical": "https://example.com/a",
            "userCanonical": "https://example.com/a",
            "crawledAs": "MOBILE",
            "sitemap": ["https://example.com/sitemap.xml"],
            "referringUrls": ["https://example.com/"],
        },
        "mobileUsabilityResult": {
            "verdict": "FAIL",
            "issues": [{"issueType": "TEXT_TOO_SMALL", "severity": "ERROR", "message": "Мелкий шрифт"}],
        },
        "ampResult": {"verdict": "PASS", "issues": [{"issueMessage": "amp warn", "severity": "WARNING"}]},
        "richResultsResult": {
            "verdict": "PARTIAL",
            "detectedItems": [
                {
                    "richResultType": "Breadcrumbs",
                    "items": [{"name": "Unnamed item", "issues": [{"issueMessage": "No item", "severity": "WARNING"}]}],
                }
            ],
        },
    }
}


def client(handler, tmp_path: Path, **kwargs) -> gsc.SearchConsole:
    return gsc.SearchConsole(
        transport=httpx.MockTransport(handler),
        quota=InspectionQuota(tmp_path / "q.json"),
        sleep=lambda _: None,
        **kwargs,
    )


def test_list_properties_and_kind(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/webmasters/v3/sites"
        assert request.headers["Authorization"] == "Bearer test-token"
        return json_response(
            200,
            {
                "siteEntry": [
                    {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
                    {"siteUrl": "https://example.com/", "permissionLevel": "siteFullUser"},
                ]
            },
        )

    props = client(handler, tmp_path).list_properties()
    assert [(p.site_url, p.kind) for p in props] == [
        ("sc-domain:example.com", "domain"),
        ("https://example.com/", "url-prefix"),
    ]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://blog.example.com/post", "sc-domain:example.com"),  # доменный важнее URL-prefix
        ("http://example.com/", "sc-domain:example.com"),  # любая схема
        ("https://shop.other.org/catalog/x", "https://shop.other.org/catalog/"),  # самый длинный prefix
        ("https://shop.other.org/about", "https://shop.other.org/"),
        ("http://shop.other.org/catalog/x", None),  # у prefix-ресурса схема важна
        ("https://notexample.com/", None),  # не поддомен
        ("https://unverified.net/", None),  # siteUnverifiedUser не считается
        ("not a url", None),
    ],
)
def test_property_for(url: str, expected: str | None) -> None:
    props = [
        gsc.Property(site_url="sc-domain:example.com", permission_level="siteOwner"),
        gsc.Property(site_url="https://blog.example.com/", permission_level="siteOwner"),
        gsc.Property(site_url="https://shop.other.org/", permission_level="siteOwner"),
        gsc.Property(site_url="https://shop.other.org/catalog/", permission_level="siteOwner"),
        gsc.Property(site_url="sc-domain:unverified.net", permission_level="siteUnverifiedUser"),
    ]
    assert gsc.property_for(url, props) == expected


def test_default_range() -> None:
    start, end = gsc.default_range(dt.date(2026, 9, 27))
    assert (start, end) == (dt.date(2026, 8, 28), dt.date(2026, 9, 24))
    assert (end - start).days == 27


def test_iter_search_analytics_pages_through_results(tmp_path: Path) -> None:
    bodies: list[dict] = []
    all_rows = [{"keys": [f"https://example.com/{i}", f"q{i}"], "clicks": i, "impressions": 10 * i} for i in range(5)]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path == b"/webmasters/v3/sites/sc-domain%3Aexample.com/searchAnalytics/query"
        body = json.loads(request.content)
        bodies.append(body)
        chunk = all_rows[body["startRow"] : body["startRow"] + body["rowLimit"]]
        return json_response(200, {"rows": chunk} if chunk else {})

    rows = list(
        client(handler, tmp_path).iter_search_analytics(
            "sc-domain:example.com", "2026-01-01", dt.date(2026, 1, 31), ["page", "query"], page_size=2
        )
    )
    assert [r.keys["page"] for r in rows] == [f"https://example.com/{i}" for i in range(5)]
    assert rows[3].keys == {"page": "https://example.com/3", "query": "q3"}
    assert rows[3].clicks == 3 and rows[3].impressions == 30
    assert [b["startRow"] for b in bodies] == [0, 2, 4]
    assert bodies[0]["startDate"] == "2026-01-01" and bodies[0]["endDate"] == "2026-01-31"
    assert bodies[0]["dataState"] == "final" and bodies[0]["type"] == "web"


def test_iter_search_analytics_limit_and_filters(tmp_path: Path) -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        return json_response(200, {"rows": [{"keys": ["x"]}] * body["rowLimit"]})

    rows = list(
        client(handler, tmp_path).iter_search_analytics(
            "sc-domain:example.com",
            filters=[{"dimension": "page", "operator": "contains", "expression": "/blog/"}],
            limit=3,
            page_size=2,
        )
    )
    assert len(rows) == 3
    assert [b["rowLimit"] for b in bodies] == [2, 1]
    assert bodies[0]["dimensionFilterGroups"][0]["filters"][0]["expression"] == "/blog/"
    start, end = gsc.default_range()
    assert bodies[0]["startDate"] == start.isoformat() and bodies[0]["endDate"] == end.isoformat()


def test_forbidden_site_is_property_not_found(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return google_error(403, "User does not have sufficient permission for site", "forbidden")

    with pytest.raises(gsc.PropertyNotFound) as exc:
        client(handler, tmp_path).get_property("sc-domain:nope.com")
    assert exc.value.site_url == "sc-domain:nope.com"
    assert exc.value.exit_code == 2
    assert "sufficient permission" in exc.value.message


def test_unauthorized_is_not_authorized(tmp_path: Path) -> None:
    with pytest.raises(gsc.NotAuthorized) as exc:
        client(lambda r: google_error(401, "Invalid Credentials"), tmp_path).list_properties()
    assert exc.value.exit_code == 3


def test_server_error_is_api_error(tmp_path: Path) -> None:
    with pytest.raises(gsc.ApiError) as exc:
        client(lambda r: google_error(500, "backend"), tmp_path).list_properties()
    assert exc.value.status == 500


def test_inspect_url_parses_everything(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/urlInspection/index:inspect"
        assert json.loads(request.content) == {
            "inspectionUrl": "https://example.com/a",
            "siteUrl": "sc-domain:example.com",
            "languageCode": "ru",
        }
        return json_response(200, INSPECT_RESPONSE)

    sc = client(handler, tmp_path)
    r = sc.inspect_url("https://example.com/a", "sc-domain:example.com")
    assert (r.verdict, r.coverage_state, r.crawled_as) == ("PASS", "Submitted and indexed", "MOBILE")
    assert r.google_canonical == r.user_canonical == "https://example.com/a"
    assert r.sitemaps == ["https://example.com/sitemap.xml"]
    assert r.referring_urls == ["https://example.com/"]
    assert r.mobile_verdict == "FAIL" and r.mobile_issues[0].type == "TEXT_TOO_SMALL"
    assert r.mobile_issues[0].message == "Мелкий шрифт"
    assert r.amp_issues[0].severity == "WARNING"
    assert r.rich_results_verdict == "PARTIAL"
    assert r.rich_results[0].type == "Breadcrumbs"
    assert r.rich_results[0].items[0].issues[0].message == "No item"
    assert r.raw["indexStatusResult"]["verdict"] == "PASS"
    assert sc.quota_remaining("sc-domain:example.com") == 1999


def test_inspect_url_outside_property(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return google_error(403, "URL is not part of this property", "forbidden")

    with pytest.raises(gsc.PropertyNotFound):
        client(handler, tmp_path).inspect_url("https://other.com/", "sc-domain:example.com")


def _site_ok(request: httpx.Request) -> httpx.Response | None:
    if request.url.path.startswith("/webmasters/v3/sites/"):
        return json_response(200, {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"})
    return None


def test_inspect_many_yields_errors_and_continues(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if (site := _site_ok(request)) is not None:
            return site
        url = json.loads(request.content)["inspectionUrl"]
        if url.endswith("/bad"):
            return google_error(400, "Invalid URL", "badRequest")
        return json_response(200, INSPECT_RESPONSE)

    urls = ["https://example.com/a", "https://example.com/bad", "https://example.com/c", "https://example.com/d"]
    results = list(client(handler, tmp_path).inspect_many(urls, "sc-domain:example.com", limit=3))
    assert [type(r).__name__ for r in results] == ["Inspection", "InspectionError", "Inspection"]
    error = results[1]
    assert isinstance(error, gsc.InspectionError)
    assert error.url == "https://example.com/bad" and error.status == 400


def test_inspect_many_stops_on_daily_quota_keeping_results(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if (site := _site_ok(request)) is not None:
            return site
        calls += 1
        if calls > 2:
            return google_error(429, "Quota exceeded for quota metric 'Queries per day'", "rateLimitExceeded")
        return json_response(200, INSPECT_RESPONSE)

    sc = client(handler, tmp_path)
    got: list = []
    with pytest.raises(gsc.QuotaExceeded) as exc:
        for item in sc.inspect_many([f"https://example.com/{i}" for i in range(10)], "sc-domain:example.com"):
            got.append(item)
    assert len(got) == 2
    assert exc.value.daily is True
    assert exc.value.retry_after is not None and 0 < exc.value.retry_after <= 86400
    assert calls == 3  # дневную квоту не повторяют
    assert sc.quota_remaining("sc-domain:example.com") == 0
    with pytest.raises(gsc.QuotaExceeded):  # учёт помнит: следующий вызов даже не идёт в сеть
        sc.inspect_url("https://example.com/x", "sc-domain:example.com")
    assert calls == 3


def test_inspect_retries_minute_quota(tmp_path: Path) -> None:
    calls = 0
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls <= 3:  # 1 запрос + 2 повтора HttpProvider → QuotaExceeded(minute) → пауза и заново
            return google_error(429, "Quota exceeded for 'Queries per minute'", "rateLimitExceeded")
        return json_response(200, INSPECT_RESPONSE)

    sc = gsc.SearchConsole(
        transport=httpx.MockTransport(handler), quota=InspectionQuota(tmp_path / "q.json"), sleep=slept.append
    )
    assert sc.inspect_url("https://example.com/a", "sc-domain:example.com").verdict == "PASS"
    assert slept == [60.0]


def test_local_quota_counter_is_per_property_and_day(tmp_path: Path) -> None:
    quota = InspectionQuota(tmp_path / "q.json", limit=2)
    quota.record("sc-domain:a.com")
    assert quota.remaining("sc-domain:a.com") == 1
    assert quota.remaining("sc-domain:b.com") == 2
    data = json.loads((tmp_path / "q.json").read_text())
    data["sc-domain:a.com"]["day"] = "2000-01-01"  # вчерашний учёт не считается
    (tmp_path / "q.json").write_text(json.dumps(data))
    assert quota.remaining("sc-domain:a.com") == 2
    (tmp_path / "q.json").write_text("not json")
    assert quota.remaining("sc-domain:a.com") == 2


def test_rate_limiter_waits_when_window_full() -> None:
    now = [0.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(2, 10.0, clock=lambda: now[0], sleep=sleep)
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()
    assert slept == [10.0]


def test_sitemaps(tmp_path: Path) -> None:
    seen: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.raw_path))
        if request.method == "PUT":
            return httpx.Response(204)
        if request.url.raw_path.endswith(b"/sitemaps"):
            return json_response(200, {"sitemap": [{"path": "https://example.com/sitemap.xml", "errors": "2"}]})
        return json_response(200, {"path": "https://example.com/sitemap.xml", "isPending": True, "warnings": "1"})

    sc = client(handler, tmp_path)
    assert sc.list_sitemaps("sc-domain:example.com")[0].errors == 2
    one = sc.get_sitemap("sc-domain:example.com", "https://example.com/sitemap.xml")
    assert one.is_pending is True and one.warnings == 1
    sc.submit_sitemap("sc-domain:example.com", "https://example.com/sitemap.xml")
    assert seen[-1] == (
        "PUT",
        b"/webmasters/v3/sites/sc-domain%3Aexample.com/sitemaps/https%3A%2F%2Fexample.com%2Fsitemap.xml",
    )
    with pytest.raises(gsc.CliError):
        sc.submit_sitemap("sc-domain:example.com", "sitemap.xml")
