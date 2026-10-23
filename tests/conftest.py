"""Shared fixtures: no real keychain, no foreign env vars, a private quota file; rerun a test file under the CI
environment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

# Typer reads these once, at import, and then forces terminal output — what a CI runner sets.
CI_ENV = {"GITHUB_ACTIONS": "true", "FORCE_COLOR": "1", "PY_COLORS": "1"}

SA_INFO = {
    "type": "service_account",
    "client_email": "reader@demo.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
    "token_uri": "https://oauth2.googleapis.com/token",
}


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[tuple[str, str], str]:
    """Каждый тест — без настоящего keychain, без чужих переменных окружения и со своим файлом квоты."""
    for name in (
        "GSC_GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        "GSC_PAGESPEED_API_KEY",
        "GOOGLE_PAGESPEED_API_KEY",
        "GOOGLE_OAUTH_SERVICE_ACCOUNT_JSON",
        "GOOGLE_OAUTH_SERVICE_ACCOUNT_FILE",
        "GOOGLE_OAUTH_PAGESPEED_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr("gsc.credentials.manager.keyring.set_password", lambda s, u, p: store.__setitem__((s, u), p))
    monkeypatch.setattr("gsc.credentials.manager.keyring.get_password", lambda s, u: store.get((s, u)))
    monkeypatch.setattr("gsc.credentials.manager.keyring.delete_password", lambda s, u: store.pop((s, u), None))
    monkeypatch.setattr("platformdirs.user_state_dir", lambda *a, **k: str(tmp_path / "state"))
    monkeypatch.setattr("gsc.providers.http.time.sleep", lambda _: None)  # повторы HttpProvider — без ожидания
    return store


@pytest.fixture
def fake_keyring(isolated: dict[tuple[str, str], str]) -> dict[tuple[str, str], str]:
    return isolated


@pytest.fixture
def sa_env(monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("GSC_GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps(SA_INFO))
    return SA_INFO


class FakeCreds:
    """Вместо google-auth: всегда валидный токен, без похода в oauth2.googleapis.com."""

    valid = True
    token = "test-token"  # noqa: S105 — фиктивный токен для тестов


@pytest.fixture
def no_token_exchange(monkeypatch: pytest.MonkeyPatch, sa_env: dict) -> None:
    monkeypatch.setattr("gsc.core.auth.google_credentials", lambda readonly=True: FakeCreds())


Handler = Callable[[httpx.Request], httpx.Response]


def json_response(status: int, body: Any) -> httpx.Response:
    return httpx.Response(status, json=body)


def google_error(status: int, message: str, reason: str = "", grpc: str = "") -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"code": status, "message": message, "status": grpc, "errors": [{"reason": reason}]}}
    )


@pytest.fixture
def same_in_ci(request: pytest.FixtureRequest) -> Callable[[str], None]:
    """Rerun this file's tests matching `-k` under CI_ENV in a fresh interpreter: the only way to set a value read at import."""
    if request.config.getoption("--snapshot-update"):
        pytest.skip("the snapshots are being written; there is nothing to compare yet")

    def run(selection: str) -> None:
        options = ["-k", selection, "-p", "no:cacheprovider", "--no-cov", "-q"]
        command = [sys.executable, "-m", "pytest", str(request.path), *options]
        env = {**os.environ, **CI_ENV}
        result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)  # noqa: S603
        assert result.returncode == 0, result.stdout[-3000:]

    return run
