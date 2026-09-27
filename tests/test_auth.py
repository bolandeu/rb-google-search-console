from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
import keyring.errors
import pytest

import gsc
from gsc.core import auth

from .conftest import SA_INFO, json_response
from .test_cli import invoke, invoke_json

# Общий слот google-oauth — один на все Google-инструменты.
SA_SLOT = ("google-oauth:service_account", "default")
PSI_SLOT = ("google-oauth:api_key", "pagespeed")


def test_auth_status_missing() -> None:
    status = gsc.auth_status()
    assert (status.google, status.pagespeed_key, status.account) == ("missing", False, None)
    assert "gsc auth login" in (status.detail or "")


def test_missing_credentials_raise_not_authorized() -> None:
    with pytest.raises(gsc.NotAuthorized) as exc:
        gsc.SearchConsole(transport=httpx.MockTransport(lambda r: json_response(200, {}))).list_properties()
    assert exc.value.exit_code == 3
    assert "gsc auth login" in (exc.value.action or "")


@pytest.mark.parametrize("var", ["GSC_GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SERVICE_ACCOUNT_JSON"])
def test_service_account_from_env(monkeypatch: pytest.MonkeyPatch, var: str) -> None:
    monkeypatch.setenv(var, json.dumps(SA_INFO))
    status = gsc.auth_status()
    assert (status.google, status.account, status.source) == ("ok", SA_INFO["client_email"], "env")


def test_service_account_from_file_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key = tmp_path / "key.json"
    key.write_text(json.dumps(SA_INFO))
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(key))
    assert gsc.auth_status().source == "file"
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(tmp_path / "nope.json"))
    status = gsc.auth_status()
    assert status.google == "missing" and "nope.json" in (status.detail or "")


def test_broken_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GSC_GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps({"type": "authorized_user"}))
    assert gsc.auth_status().google == "missing"
    with pytest.raises(gsc.NotAuthorized):
        auth.load_service_account()
    monkeypatch.setenv("GSC_GOOGLE_SERVICE_ACCOUNT_JSON", "{not json")
    assert "не JSON" in (gsc.auth_status().detail or "")
    monkeypatch.setenv("GSC_GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps({"type": "service_account"}))
    assert "client_email" in (gsc.auth_status().detail or "")


def test_check_reports_revoked_key(monkeypatch: pytest.MonkeyPatch, sa_env: dict) -> None:
    def revoked(creds) -> str:
        raise gsc.NotAuthorized("google", "invalid_grant", action="…")

    monkeypatch.setattr(auth, "google_credentials", lambda readonly=True: object())
    monkeypatch.setattr(auth, "refresh_token", revoked)
    status = gsc.auth_status(check=True)
    assert status.google == "expired" and status.detail == "invalid_grant"


def test_refresh_token_maps_google_auth_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    import google.auth.exceptions

    class Creds:
        def __init__(self, exc: Exception) -> None:
            self.exc = exc

        def refresh(self, request) -> None:
            raise self.exc

    with pytest.raises(gsc.NotAuthorized):
        auth.refresh_token(Creds(google.auth.exceptions.RefreshError("invalid_grant")))
    with pytest.raises(gsc.ApiError):
        auth.refresh_token(Creds(google.auth.exceptions.TransportError("offline")))


def test_google_credentials_builds_scoped_service_account(monkeypatch: pytest.MonkeyPatch, sa_env: dict) -> None:
    from google.oauth2 import service_account

    captured: dict = {}
    monkeypatch.setattr(
        service_account.Credentials,
        "from_service_account_info",
        classmethod(lambda cls, info, scopes: captured.update(info=info, scopes=scopes) or "creds"),
    )
    assert auth.google_credentials(readonly=False) == "creds"
    assert captured["scopes"] == [auth.SCOPE_FULL] and captured["info"]["client_email"] == SA_INFO["client_email"]


def test_import_has_no_side_effects() -> None:
    """import gsc не тянет CLI и google-auth (отдельный процесс — в этом их уже импортировали другие тесты)."""
    code = "import sys, gsc; print('typer' in sys.modules, 'google.auth' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)  # noqa: S603
    assert out.stdout.split() == ["False", "False"]


# --- CLI: gsc auth ----------------------------------------------------------------


def test_login_from_file_then_status_and_logout(tmp_path: Path, fake_keyring) -> None:
    key = tmp_path / "key.json"
    key.write_text(json.dumps(SA_INFO))
    code, payload = invoke_json("auth", "login", "--file", str(key))
    assert code == 0 and payload["account"] == SA_INFO["client_email"]
    assert SA_SLOT in fake_keyring

    _, payload = invoke_json("auth", "status")
    assert (payload["google"], payload["source"]) == ("ok", "keychain")

    assert invoke("auth", "logout").exit_code == 0
    _, payload = invoke_json("auth", "status")
    assert payload["google"] == "missing"


def test_login_rejects_non_service_account_file(tmp_path: Path) -> None:
    key = tmp_path / "key.json"
    key.write_text(json.dumps({"type": "authorized_user"}))
    code, payload = invoke_json("auth", "login", "--file", str(key))
    assert code == 2 and payload["error"]["code"] == "INVALID_ARGUMENTS"


def test_login_non_interactive_needs_source() -> None:
    code, payload = invoke_json("--non-interactive", "auth", "login")
    assert code == 2 and "--file" in payload["error"]["message"]
    code, _ = invoke_json("auth", "login", "--provider", "pagespeed", "--non-interactive")
    assert code == 2


def test_login_google_from_env_and_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_keyring) -> None:
    code, _ = invoke_json("auth", "login", env={"GSC_GOOGLE_SERVICE_ACCOUNT_JSON": json.dumps(SA_INFO)})
    assert code == 0 and SA_SLOT in fake_keyring
    fake_keyring.clear()
    key = tmp_path / "key.json"
    key.write_text(json.dumps(SA_INFO))
    result = invoke("auth", "login", input=f"{key}\n")
    assert result.exit_code == 0 and SA_SLOT in fake_keyring


def test_login_pagespeed_prompt_and_env(fake_keyring) -> None:
    assert invoke("auth", "login", "--provider", "pagespeed", input="  psi-key \n").exit_code == 0
    assert fake_keyring[PSI_SLOT] == "psi-key"
    assert gsc.auth_status().pagespeed_key is True
    code, _ = invoke_json("auth", "login", "--provider", "pagespeed", env={"GSC_PAGESPEED_API_KEY": "env-key"})
    assert code == 0 and fake_keyring[PSI_SLOT] == "env-key"


def test_env_var_works_when_keyring_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_get_password(service: str, username: str) -> str | None:
        raise keyring.errors.NoKeyringError("no backend")

    monkeypatch.setattr("gsc.credentials.manager.keyring.get_password", broken_get_password)
    monkeypatch.setenv("GSC_PAGESPEED_API_KEY", "k")
    assert gsc.auth_status().pagespeed_key is True


def test_human_auth_status(sa_env: dict) -> None:
    result = invoke("auth", "status")
    assert result.exit_code == 0 and SA_INFO["client_email"] in result.stdout


def test_doctor_reports_credential_checks(tmp_path: Path, sa_env: dict) -> None:
    _, payload = invoke_json("--project", str(tmp_path), "doctor")
    checks = {check["name"]: check for check in payload["checks"]}
    assert "credential_store" in checks
    assert checks["credential:google"]["ok"] is True
    assert checks["credential:pagespeed"]["ok"] is False


def test_keys_are_shared_with_other_google_tools(fake_keyring) -> None:
    """Ключ, положенный любым Google-инструментом в общий слот, виден gsc — и наоборот."""
    from google_oauth import GoogleAuth, Profile

    other = GoogleAuth(Profile(cli_name="other", service="Другой", scopes=("s",)))
    other.store_service_account(json.dumps(SA_INFO))
    assert fake_keyring[SA_SLOT] == json.dumps(SA_INFO)
    assert gsc.auth_status().source == "keychain"


@pytest.mark.parametrize(
    ("var", "value"),
    [("GOOGLE_PAGESPEED_API_KEY", "legacy"), ("GOOGLE_OAUTH_PAGESPEED_API_KEY", "shared")],
)
def test_pagespeed_env_overrides_keychain(fake_keyring, monkeypatch: pytest.MonkeyPatch, var: str, value: str) -> None:
    fake_keyring[PSI_SLOT] = "stored"
    monkeypatch.setenv(var, value)
    assert auth.pagespeed_key() == value


def test_revoked_key_via_real_refresh_path(monkeypatch: pytest.MonkeyPatch, sa_env: dict) -> None:
    """RefreshError google-auth → NotAuthorized из google-oauth = gsc.NotAuthorized (публичный тип не сменился)."""
    import google.auth.exceptions

    class Revoked:
        def refresh(self, request) -> None:
            raise google.auth.exceptions.RefreshError("invalid_grant")

    monkeypatch.setattr(auth, "google_credentials", lambda readonly=True: Revoked())
    status = gsc.auth_status(check=True)
    assert status.google == "expired" and "invalid_grant" in (status.detail or "")
    assert issubclass(gsc.NotAuthorized, gsc.CliError)
