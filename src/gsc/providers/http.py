from __future__ import annotations

import functools
import logging
import time
from typing import Any

import httpx

from ..core.errors import AuthRequired, CliError, ProviderError
from ..core.version import DEV_VERSION, installed_version

_PACKAGE_NAME = __name__.split(".")[0]
log = logging.getLogger(__name__)

# Responses worth retrying: the server said "not now", not "no".
_RETRY_STATUSES = frozenset({429, 502, 503, 504})


class HttpProvider:
    """Base class for one HTTP API integration.

    Subclass per service: set `name` and `base_url`, override
    `auth_headers()` to inject the credential (read it via
    `credentials.manager`, never from config), then add typed methods that
    call `self.request(...)` / `self.get_json(...)`. What the wire can throw
    at you is handled once, here:

    - 401 / 403                       -> AuthRequired (exit 3)
    - 429 / 502 / 503 / 504, timeouts,
      connection errors               -> retried `retries` times with
                                         exponential backoff, then
                                         ProviderError (exit 5)
    - any other 4xx / 5xx             -> ProviderError with the status
    - non-JSON body from get_json     -> ProviderError

    A service with its own error body overrides `error_for` (build the
    CliError for a final error response) and `should_retry` (e.g. never
    retry an exhausted daily quota). `auth_headers()` is called per request,
    so a short-lived token can refresh itself there.

    `transport` exists for tests (`httpx.MockTransport`); leave it None
    in real code.
    """

    name: str = "default"
    base_url: str = ""
    timeout: float = 30.0
    retries: int = 2
    backoff: float = 1.0
    transport: httpx.BaseTransport | None = None

    def auth_headers(self) -> dict[str, str]:
        return {}

    @functools.cached_property
    def client(self) -> httpx.Client:
        user_agent = f"{_PACKAGE_NAME}/{installed_version() or DEV_VERSION}"
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"User-Agent": user_agent},
            transport=self.transport,
        )

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send one request and return a successful (2xx/3xx) response, or raise a CliError."""
        attempt = 0
        while True:
            try:
                # Per request, not per client: a short-lived token (Google's lasts 1 h) gets refreshed here.
                headers = {**self.auth_headers(), **kwargs.pop("headers", {})}
                response = self.client.request(method, path, headers=headers, **kwargs)
            except httpx.TransportError as exc:
                if attempt < self.retries:
                    self._sleep(attempt, None)
                    attempt += 1
                    continue
                raise ProviderError(
                    self.name,
                    f"{type(exc).__name__} while calling {method} {path}",
                    action="Check the network connection and the provider's status, then retry.",
                ) from exc

            status = response.status_code
            if status in _RETRY_STATUSES and attempt < self.retries and self.should_retry(response):
                self._sleep(attempt, response.headers.get("Retry-After"))
                attempt += 1
                continue
            if response.is_error:
                raise self.error_for(response, f"{method} {path}")
            return response

    def should_retry(self, response: httpx.Response) -> bool:
        """Whether a 429/5xx is worth retrying. Override to say no, e.g. to an exhausted *daily* quota."""
        return True

    def error_for(self, response: httpx.Response, call: str) -> CliError:
        """The CliError for a final error response. Override to map a service's own error body; call super() last."""
        status = response.status_code
        if status in (401, 403):
            return AuthRequired(self.name)
        return ProviderError(
            self.name,
            f"HTTP {status} for {call}: {response.text[:200]}",
            status=status,
            action="Retry later." if status in _RETRY_STATUSES else None,
        )

    def get_json(self, path: str, **params: Any) -> Any:
        return self.request_json("GET", path, params=params or None)

    def request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(
                self.name, f"non-JSON response for {method} {path}", status=response.status_code
            ) from exc

    def _sleep(self, attempt: int, retry_after: str | None) -> None:
        delay = self.backoff * (2**attempt)
        if retry_after and retry_after.isdigit():
            delay = max(delay, float(retry_after))
        log.debug("%s: retrying in %.1fs (attempt %d/%d)", self.name, delay, attempt + 1, self.retries)
        time.sleep(delay)
