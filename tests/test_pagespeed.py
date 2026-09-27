from __future__ import annotations

import copy
import threading
from typing import Any

import httpx
import pytest

import gsc
from gsc.core.quota import RateLimiter

from .conftest import google_error, json_response

# Сокращённый ответ runPagespeed v5 — структура по документации PSI / Lighthouse 12.
PSI_RESPONSE: dict[str, Any] = {
    "id": "https://example.com/",
    "loadingExperience": {
        "id": "https://example.com/",
        "overall_category": "AVERAGE",
        "metrics": {
            "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2600, "category": "AVERAGE"},
            "INTERACTION_TO_NEXT_PAINT": {"percentile": 180, "category": "FAST"},
            "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 12, "category": "AVERAGE"},
            "FIRST_CONTENTFUL_PAINT_MS": {"percentile": 1500, "category": "FAST"},
            "EXPERIMENTAL_TIME_TO_FIRST_BYTE": {"percentile": 700, "category": "FAST"},
        },
    },
    "originLoadingExperience": {
        "id": "https://example.com",
        "overall_category": "FAST",
        "metrics": {"LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2100, "category": "FAST"}},
    },
    "lighthouseResult": {
        "requestedUrl": "https://example.com/",
        "finalDisplayedUrl": "https://www.example.com/",
        "lighthouseVersion": "12.2.1",
        "fetchTime": "2026-09-27T08:00:00.000Z",
        "categories": {
            "performance": {"id": "performance", "title": "Performance", "score": 0.72},
            "seo": {"id": "seo", "title": "SEO", "score": 1},
        },
        "audits": {
            "largest-contentful-paint": {
                "id": "largest-contentful-paint",
                "title": "Largest Contentful Paint",
                "score": 0.5,
                "scoreDisplayMode": "numeric",
                "displayValue": "3.1 s",
                "numericValue": 3120.5,
                "numericUnit": "millisecond",
            },
            "first-contentful-paint": {"id": "first-contentful-paint", "numericValue": 1200},
            "total-blocking-time": {"id": "total-blocking-time", "numericValue": 250},
            "cumulative-layout-shift": {"id": "cumulative-layout-shift", "numericValue": 0.08},
            "speed-index": {"id": "speed-index", "numericValue": 2900},
            "interactive": {"id": "interactive", "numericValue": 4100},
            "render-blocking-resources": {
                "id": "render-blocking-resources",
                "title": "Eliminate render-blocking resources",
                "score": 0,
                "scoreDisplayMode": "metricSavings",
                "displayValue": "Potential savings of 450 ms",
                "details": {
                    "type": "opportunity",
                    "overallSavingsMs": 450,
                    "overallSavingsBytes": 12000,
                    "items": [{"url": "https://example.com/app.css", "wastedMs": 450}],
                },
                "metricSavings": {"FCP": 450, "LCP": 300},
            },
            "diagnostics": {"id": "diagnostics", "scoreDisplayMode": "informative", "details": {"type": "debugdata"}},
        },
    },
}


def ps(handler, **kwargs) -> gsc.PageSpeed:
    return gsc.PageSpeed(transport=httpx.MockTransport(handler), limiter=RateLimiter(1000, 1.0), **kwargs)


def test_analyze_parses_full_response() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(200, PSI_RESPONSE)

    r = ps(handler, api_key="k").analyze("https://example.com/", "desktop", ["performance", "best-practices"])
    params = seen[0].url.params
    assert seen[0].url.path == "/pagespeedonline/v5/runPagespeed"
    assert params.get_list("category") == ["PERFORMANCE", "BEST_PRACTICES"]
    assert params["strategy"] == "desktop" and params["key"] == "k"

    assert r.url == "https://example.com/" and r.final_url == "https://www.example.com/"
    assert r.lighthouse_version == "12.2.1"
    assert r.scores == {"performance": 0.72, "seo": 1}
    assert r.lab.lcp_ms == 3120.5 and r.lab.cls == 0.08 and r.lab.tti_ms == 4100
    assert r.crux_url is not None and r.crux_url.lcp is not None
    assert (r.crux_url.lcp.percentile, r.crux_url.lcp.category) == (2600, "AVERAGE")
    assert r.crux_url.cls is not None and r.crux_url.cls.value == 0.12  # CLS×100 в ответе → 0.12
    assert r.crux_origin is not None and r.crux_origin.overall_category == "FAST"
    assert r.crux_origin.inp is None
    assert r.crux_origin_fallback is False
    assert len(r.audits) == len(PSI_RESPONSE["lighthouseResult"]["audits"])
    rbr = r.audit("render-blocking-resources")
    assert rbr is not None
    assert (rbr.savings_ms, rbr.savings_bytes, rbr.details_type) == (450, 12000, "opportunity")
    assert rbr.details == [{"url": "https://example.com/app.css", "wastedMs": 450}]
    assert rbr.metric_savings == {"FCP": 450, "LCP": 300}
    diag = r.audit("diagnostics")
    assert diag is not None and diag.details == []
    assert r.audit("missing") is None


def test_origin_fallback() -> None:
    data = copy.deepcopy(PSI_RESPONSE)
    data["loadingExperience"]["origin_fallback"] = True
    r = gsc.parse_pagespeed("https://example.com/deep", "mobile", data)
    assert r.crux_url is None and r.crux_origin_fallback is True
    assert gsc.parse_pagespeed("u", "mobile", {}).crux_origin is None


def test_key_comes_from_credentials(fake_keyring, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_PAGESPEED_API_KEY", "legacy-key")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(200, PSI_RESPONSE)

    ps(handler).analyze("https://example.com/")
    assert seen[0].url.params["key"] == "legacy-key"


def test_keyless_zero_quota_is_not_authorized() -> None:
    body = {
        "error": {
            "code": 429,
            "message": "Quota exceeded for quota metric 'Queries' and limit 'Queries per day'",
            "status": "RESOURCE_EXHAUSTED",
            "details": [{"reason": "RATE_LIMIT_EXCEEDED", "metadata": {"quota_limit_value": "0"}}],
        }
    }
    with pytest.raises(gsc.NotAuthorized) as exc:
        ps(lambda r: json_response(429, body)).analyze("https://example.com/")
    assert "--provider pagespeed" in (exc.value.action or "")


def test_bad_key_is_not_authorized() -> None:
    with pytest.raises(gsc.NotAuthorized):
        ps(lambda r: google_error(400, "API key not valid", "badRequest"), api_key="bad").analyze("https://x.com/")


def test_invalid_arguments() -> None:
    client = ps(lambda r: json_response(200, PSI_RESPONSE), api_key="k")
    with pytest.raises(gsc.CliError):
        client.analyze("https://example.com/", "tablet")
    with pytest.raises(gsc.CliError):
        client.analyze("https://example.com/", "mobile", ["speed"])


def test_analyze_many_mixes_results_and_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "bad" in request.url.params["url"]:
            return google_error(400, "Lighthouse returned error: FAILED_DOCUMENT_REQUEST", "badRequest")
        return json_response(200, PSI_RESPONSE)

    urls = [f"https://example.com/{i}" for i in range(6)] + ["https://example.com/bad"]
    results = list(ps(handler, api_key="k").analyze_many(urls, concurrency=2))
    assert len(results) == 7
    errors = [r for r in results if isinstance(r, gsc.PageSpeedError)]
    assert [e.url for e in errors] == ["https://example.com/bad"]
    assert errors[0].status == 400
    assert {r.url for r in results if isinstance(r, gsc.PageSpeedResult)} == set(urls[:6])


def test_analyze_many_stops_on_daily_quota() -> None:
    lock = threading.Lock()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        with lock:
            calls += 1
            n = calls
        if n > 2:
            return google_error(429, "Quota exceeded for 'Queries per day'", "rateLimitExceeded")
        return json_response(200, PSI_RESPONSE)

    got: list = []
    with pytest.raises(gsc.QuotaExceeded):
        for item in ps(handler, api_key="k").analyze_many([f"https://e.com/{i}" for i in range(50)], concurrency=1):
            got.append(item)
    assert len(got) == 2
