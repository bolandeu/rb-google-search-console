from __future__ import annotations

import json

import httpx
import pytest

import gsc
from gsc.core.quota import RateLimiter

from .conftest import json_response

# Формат — по живым ответам CrUX API (ost-term.ru, сентябрь 2026).
RECORD = {
    "record": {
        "key": {"origin": "https://ost-term.ru"},
        "metrics": {
            "largest_contentful_paint": {
                "histogram": [
                    {"start": 0, "end": 2500, "density": 0.8813},
                    {"start": 2500, "end": 4000, "density": 0.0876},
                    {"start": 4000, "density": 0.0311},
                ],
                "percentiles": {"p75": 1884},
            },
            "cumulative_layout_shift": {
                "histogram": [
                    {"start": "0.00", "end": "0.10", "density": 0.9741},
                    {"start": "0.10", "end": "0.25", "density": 0.0205},
                    {"start": "0.25", "density": 0.0054},
                ],
                "percentiles": {"p75": "0.05"},
            },
            "form_factors": {"fractions": {"desktop": 0.4836, "phone": 0.5164, "tablet": 0}},
            "largest_contentful_paint_image_time_to_first_byte": {"percentiles": {"p75": 873}},
        },
        "collectionPeriod": {
            "firstDate": {"year": 2026, "month": 8, "day": 29},
            "lastDate": {"year": 2026, "month": 9, "day": 25},
        },
    },
    "urlNormalizationDetails": {"originalUrl": "https://ost-term.ru", "normalizedUrl": "https://ost-term.ru/"},
}

HISTORY = {
    "record": {
        "key": {"origin": "https://ost-term.ru", "formFactor": "PHONE"},
        "metrics": {
            "largest_contentful_paint": {
                "histogramTimeseries": [
                    {"start": 0, "end": 2500, "densities": [0.9, 0.85]},
                    {"start": 2500, "end": 4000, "densities": [0.07, 0.1]},
                    {"start": 4000, "densities": [0.03, "NaN"]},
                ],
                "percentilesTimeseries": {"p75s": [1708, None]},
            },
            "navigation_types": {"fractionTimeseries": {"navigate": {"fractions": [0.8, 0.7]}}},
        },
        "collectionPeriods": [
            {"firstDate": {"year": 2026, "month": 3, "day": 8}, "lastDate": {"year": 2026, "month": 4, "day": 4}},
            {"firstDate": {"year": 2026, "month": 3, "day": 15}, "lastDate": {"year": 2026, "month": 4, "day": 11}},
        ],
    }
}


def crux(handler, **kwargs) -> gsc.CrUX:
    return gsc.CrUX(transport=httpx.MockTransport(handler), limiter=RateLimiter(1000, 1.0), **kwargs)


def test_record() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(200, RECORD)

    r = crux(handler, api_key="k").record(origin="https://ost-term.ru", form_factor="phone", metrics=["x"])
    assert seen[0].url.path == "/v1/records:queryRecord" and seen[0].url.params["key"] == "k"
    assert json.loads(seen[0].content) == {"origin": "https://ost-term.ru", "formFactor": "PHONE", "metrics": ["x"]}
    assert r is not None
    assert (r.origin, r.period and r.period.first_date, r.normalized_url) == (
        "https://ost-term.ru",
        "2026-08-29",
        "https://ost-term.ru/",
    )
    lcp = r.metrics["largest_contentful_paint"]
    assert (lcp.p75, lcp.good, lcp.needs_improvement, lcp.poor) == (1884, 0.8813, 0.0876, 0.0311)
    assert r.metrics["cumulative_layout_shift"].p75 == 0.05
    assert r.metrics["form_factors"].fractions["phone"] == 0.5164
    phase = r.metrics["largest_contentful_paint_image_time_to_first_byte"]
    assert phase.p75 == 873 and phase.good is None


def test_history() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return json_response(200, HISTORY)

    h = crux(handler, api_key="k").history("https://ost-term.ru/", periods=40)
    assert seen[0] == {"url": "https://ost-term.ru/", "collectionPeriodCount": 40}
    assert h is not None and h.form_factor == "PHONE"
    assert [p.last_date for p in h.periods] == ["2026-04-04", "2026-04-11"]
    lcp = h.metrics["largest_contentful_paint"]
    assert lcp.p75 == [1708, None] and lcp.good == [0.9, 0.85] and lcp.poor == [0.03, None]
    assert h.metrics["navigation_types"].fractions == {"navigate": [0.8, 0.7]}


def test_no_data_is_none() -> None:
    body = {"error": {"code": 404, "message": "chrome ux report data not found", "status": "NOT_FOUND"}}
    client = crux(lambda r: json_response(404, body), api_key="k")
    assert client.record("https://example.com/rare") is None
    assert client.history(origin="https://example.com") is None


def test_blocked_key_is_not_authorized() -> None:
    body = {
        "error": {
            "code": 403,
            "message": "Requests to this API chromeuxreport.googleapis.com are blocked.",
            "status": "PERMISSION_DENIED",
            "details": [{"reason": "API_KEY_SERVICE_BLOCKED"}],
        }
    }
    with pytest.raises(gsc.NotAuthorized) as exc:
        crux(lambda r: json_response(403, body), api_key="k").record(origin="https://example.com")
    assert "Chrome UX Report API" in (exc.value.action or "")


def test_server_error_is_api_error() -> None:
    with pytest.raises(gsc.ApiError):
        crux(lambda r: json_response(500, {"error": {"message": "x"}}), api_key="k").record(origin="https://e.com")


def test_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(gsc.NotAuthorized):
        crux(lambda r: json_response(200, RECORD)).record(origin="https://example.com")
    monkeypatch.setenv("GSC_PAGESPEED_API_KEY", "env-key")
    assert crux(lambda r: json_response(200, RECORD)).record(origin="https://example.com") is not None


def test_invalid_arguments() -> None:
    client = crux(lambda r: json_response(200, RECORD), api_key="k")
    with pytest.raises(gsc.CliError):
        client.record()
    with pytest.raises(gsc.CliError):
        client.record("https://a.com/", origin="https://a.com")
    with pytest.raises(gsc.CliError):
        client.record(origin="https://a.com", form_factor="watch")
    with pytest.raises(gsc.CliError):
        client.history(origin="https://a.com", periods=41)


def test_parse_helpers_tolerate_gaps() -> None:
    assert gsc.parse_crux_record({}).metrics == {}
    assert gsc.parse_crux_history({"record": {"metrics": {"m": {"percentilesTimeseries": {"p75s": ["x"]}}}}}).metrics[
        "m"
    ].p75 == [None]
