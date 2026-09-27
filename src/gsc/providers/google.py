"""HTTP-клиенты Google: Search Console (webmasters/v3 + urlInspection v1) и PageSpeed Insights v5.

Возвращают сырой JSON; разбор в модели — в core/. Здесь только транспорт и
перевод ошибок Google ({"error": {"code", "message", "status", "errors": [{"reason"}]}})
в типизированные ошибки gsc.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from ..core import auth
from ..core.errors import ApiError, CliError, NotAuthorized, PropertyNotFound, QuotaExceeded
from .http import HttpProvider

# Квоты Google сбрасываются в полночь по тихоокеанскому времени.
_QUOTA_TZ = ZoneInfo("America/Los_Angeles")
_QUOTA_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "dailyLimitExceeded"}


def seconds_until_quota_reset(now: dt.datetime | None = None) -> float:
    now = (now or dt.datetime.now(dt.UTC)).astimezone(_QUOTA_TZ)
    midnight = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight - now).total_seconds()


def quota_day(now: dt.datetime | None = None) -> str:
    """Сутки квоты Google (YYYY-MM-DD по тихоокеанскому времени)."""
    return (now or dt.datetime.now(dt.UTC)).astimezone(_QUOTA_TZ).date().isoformat()


def google_error(response: httpx.Response) -> tuple[str, str, set[str]]:
    """(message, status, reasons) из тела ошибки Google; не JSON — текст как есть."""
    try:
        error = response.json().get("error", {})
    except ValueError:
        return response.text[:300], "", set()
    if not isinstance(error, dict):
        return str(error)[:300], "", set()
    reasons = {e.get("reason", "") for e in error.get("errors", []) if isinstance(e, dict)}
    reasons |= {d.get("reason", "") for d in error.get("details", []) if isinstance(d, dict)}
    return str(error.get("message", ""))[:500], str(error.get("status", "")), reasons


def is_quota_error(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    _, status, reasons = google_error(response)
    return status == "RESOURCE_EXHAUSTED" or bool(reasons & _QUOTA_REASONS) or "RATE_LIMIT_EXCEEDED" in reasons


def _zero_quota(response: httpx.Response) -> bool:
    """Анонимная квота PSI: Google отвечает 429 с quota_limit_value = 0."""
    try:
        details = response.json().get("error", {}).get("details", [])
    except (ValueError, AttributeError):
        return False
    return any(str(d.get("metadata", {}).get("quota_limit_value")) == "0" for d in details if isinstance(d, dict))


def is_daily_quota(message: str) -> bool:
    lowered = message.lower()
    return "per day" in lowered or "daily" in lowered


def _q(value: str) -> str:
    return quote(value, safe="")


class AccessDenied(ApiError):
    """403/404 от Search Console: нет доступа к ресурсу или URL вне ресурса."""

    def __init__(self, provider: str, detail: str, *, status: int) -> None:
        super().__init__(provider, f"нет доступа: {detail}", status=status)
        self.detail = detail


class GoogleProvider(HttpProvider):
    """Общее для API Google: квоты и типичные ошибки."""

    def should_retry(self, response: httpx.Response) -> bool:
        # Дневную квоту повторами не вернуть; минутную — можно.
        return not (is_quota_error(response) and is_daily_quota(google_error(response)[0]))

    def error_for(self, response: httpx.Response, call: str) -> CliError:
        message, _, _ = google_error(response)
        if is_quota_error(response):
            daily = is_daily_quota(message)
            return QuotaExceeded(
                self.name, message, retry_after=seconds_until_quota_reset() if daily else 60.0, daily=daily
            )
        return ApiError(self.name, f"HTTP {response.status_code} для {call}: {message}", status=response.status_code)


class SearchConsoleProvider(GoogleProvider):
    name = auth.GOOGLE
    base_url = "https://searchconsole.googleapis.com/"

    def __init__(self, *, readonly: bool = True, transport: httpx.BaseTransport | None = None) -> None:
        self.readonly = readonly
        self.transport = transport
        self._creds: Any = None

    def auth_headers(self) -> dict[str, str]:
        if self._creds is None:
            self._creds = auth.google_credentials(readonly=self.readonly)
        if not self._creds.valid:
            auth.refresh_token(self._creds)
        return {"Authorization": f"Bearer {self._creds.token}"}

    def error_for(self, response: httpx.Response, call: str) -> CliError:
        message, _, _ = google_error(response)
        status = response.status_code
        if status == 401:
            return NotAuthorized(self.name, f"Google не принял токен: {message}", action=f"'{auth.LOGIN_GOOGLE}'")
        if status in (403, 404) and not is_quota_error(response):
            return AccessDenied(self.name, message, status=status)
        return super().error_for(response, call)

    @contextmanager
    def _site_errors(self, site_url: str) -> Iterator[None]:
        """403/404 на запросе к ресурсу → PropertyNotFound с именем ресурса."""
        try:
            yield
        except AccessDenied as exc:
            raise PropertyNotFound(site_url, exc.detail) from exc

    # --- вызовы API; site_url экранируется целиком, включая «:» и «/» ---------------

    def list_sites(self) -> dict:
        return self.get_json("webmasters/v3/sites")

    def get_site(self, site_url: str) -> dict:
        with self._site_errors(site_url):
            return self.get_json(f"webmasters/v3/sites/{_q(site_url)}")

    def search_analytics(self, site_url: str, body: dict) -> dict:
        with self._site_errors(site_url):
            return self.request_json("POST", f"webmasters/v3/sites/{_q(site_url)}/searchAnalytics/query", json=body)

    def inspect(self, url: str, site_url: str, language: str | None) -> dict:
        """403 здесь (URL вне ресурса / нет доступа) остаётся AccessDenied: решает вызывающий."""
        body = {"inspectionUrl": url, "siteUrl": site_url}
        if language:
            body["languageCode"] = language
        return self.request_json("POST", "v1/urlInspection/index:inspect", json=body)

    def list_sitemaps(self, site_url: str) -> dict:
        with self._site_errors(site_url):
            return self.get_json(f"webmasters/v3/sites/{_q(site_url)}/sitemaps")

    def get_sitemap(self, site_url: str, feedpath: str) -> dict:
        with self._site_errors(site_url):
            return self.get_json(f"webmasters/v3/sites/{_q(site_url)}/sitemaps/{_q(feedpath)}")

    def submit_sitemap(self, site_url: str, feedpath: str) -> None:
        with self._site_errors(site_url):
            self.request("PUT", f"webmasters/v3/sites/{_q(site_url)}/sitemaps/{_q(feedpath)}")


class PageSpeedProvider(GoogleProvider):
    name = auth.PAGESPEED
    base_url = "https://pagespeedonline.googleapis.com/pagespeedonline/v5/"
    timeout = 120.0  # Lighthouse на стороне Google идёт 10–60 с
    retries = 4
    backoff = 2.0

    def __init__(self, *, api_key: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self.transport = transport

    def error_for(self, response: httpx.Response, call: str) -> CliError:
        message, status, reasons = google_error(response)
        if is_quota_error(response) and not self.key and _zero_quota(response):
            return NotAuthorized(
                self.name,
                "Без API-ключа квота PageSpeed Insights нулевая.",
                action=f"Выполните '{auth.LOGIN_PAGESPEED}'.",
            )
        key_problem = response.status_code in (400, 403) and (
            "API_KEY_INVALID" in reasons or "API key" in message or status == "PERMISSION_DENIED"
        )
        if key_problem and not is_quota_error(response):
            return NotAuthorized(
                self.name,
                f"PageSpeed Insights отклонил ключ: {message}",
                action=f"Проверьте, что PageSpeed Insights API включён в проекте ключа, и выполните "
                f"'{auth.LOGIN_PAGESPEED}'.",
            )
        return super().error_for(response, call)

    @property
    def key(self) -> str | None:
        if self._api_key is None:
            self._api_key = auth.pagespeed_key() or ""
        return self._api_key or None

    def run(self, url: str, *, strategy: str, categories: list[str], locale: str | None) -> dict:
        params: list[tuple[str, str]] = [("url", url), ("strategy", strategy)]
        params += [("category", c.upper().replace("-", "_")) for c in categories]
        if locale:
            params.append(("locale", locale))
        if self.key:
            params.append(("key", self.key))
        return self.request_json("GET", "runPagespeed", params=params)


class CruxProvider(GoogleProvider):
    """Chrome UX Report API. Ключ — тот же API-ключ Google Cloud, что у PageSpeed (с включённым CrUX API)."""

    name = "crux"
    base_url = "https://chromeuxreport.googleapis.com/v1/"

    def __init__(self, *, api_key: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self.transport = transport

    def error_for(self, response: httpx.Response, call: str) -> CliError:
        message, status, reasons = google_error(response)
        blocked = {"API_KEY_SERVICE_BLOCKED", "SERVICE_DISABLED", "API_KEY_INVALID"} & reasons
        if (response.status_code in (400, 403) and (blocked or status == "PERMISSION_DENIED")) and not is_quota_error(
            response
        ):
            return NotAuthorized(
                self.name,
                f"Chrome UX Report API недоступен для ключа: {message}",
                action="Включите Chrome UX Report API в проекте Google Cloud ключа и добавьте его в ограничения "
                f"ключа (APIs & Services → Credentials); ключ — '{auth.LOGIN_PAGESPEED}'.",
            )
        return super().error_for(response, call)

    @property
    def key(self) -> str | None:
        if self._api_key is None:
            self._api_key = auth.pagespeed_key() or ""
        return self._api_key or None

    def query(self, method: str, body: dict) -> dict | None:
        """records:queryRecord / queryHistoryRecord; нет данных у Google (404) → None."""
        if not self.key:
            raise NotAuthorized(
                self.name, "Нет API-ключа Google для Chrome UX Report.", action=f"Выполните '{auth.LOGIN_PAGESPEED}'."
            )
        try:
            return self.request_json("POST", f"./records:{method}", params={"key": self.key}, json=body)
        except ApiError as exc:
            if exc.status == 404:
                return None
            raise
