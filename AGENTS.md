# AGENTS.md

Guidance for coding agents working on the **gsc** package
itself (not its end users — see `src/gsc/data/SKILL.md` for
that).

## Development

```bash
uv sync                          # also writes uv.lock — commit it (CI runs `uv lock --check`)
uv run gsc --help
uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest
```

Before calling anything done, that last line must pass — it's exactly
what CI runs on Linux/macOS (Windows is not supported), followed by `uv tool install .` to
prove the package still installs as a tool.

Run `scripts/install_hooks.sh` once (`.git/hooks/` isn't versioned by git,
so this is also needed again after a fresh clone). It installs a
pre-commit hook that warns — never blocks — when a command's logic changed
without its docstring changing too, since that docstring is the `--help`
text agents read as this CLI's API contract.

## Architecture (do not violate)

- `commands/` — argument parsing only. No business logic here.
- `core/` — services, models, errors. All real logic lives here.
- `providers/` — `google.py`: `SearchConsoleProvider` and `PageSpeedProvider`,
  thin `HttpProvider` subclasses returning raw JSON. Google's error body is
  mapped once, in `error_for` / `should_retry` (hooks added to the template's
  `HttpProvider`): 401 → `NotAuthorized`, 403/404 → `PropertyNotFound` (via
  `_site_errors`), 429 / 403 rateLimitExceeded → `QuotaExceeded` (daily quota is
  never retried), rest → `ApiError`. The service-account token is fetched by
  `google-auth` in `auth_headers()` — per request, so it refreshes after 1 h.
  `CruxProvider` — Chrome UX Report API with the PSI key; 404 means "no data"
  and becomes `None`. Gotcha: a relative path whose first segment has a colon
  (`records:queryRecord`) is parsed by httpx as a URL scheme — write
  `./records:…`. Tests inject `httpx.MockTransport` via `transport=`. Never
  call `httpx` from `core/` or `commands/`.
- `credentials/` — secrets via OS keychain + env vars. Never write a secret
  to `.gsc/config.toml` or any other project-local file.
- `output/` — every command supports both human and `--json` output via
  `output.emit_success` / `output.guard`. Don't `print()` directly in a
  command. stdout is data only; errors, `--verbose` progress and `logging`
  go to stderr.
- Command groups are created with `output.group("...")`, not
  `typer.Typer(...)` — that's what makes `gsc <group>` with
  no subcommand print help (exit 0) instead of a usage error.
- Errors are `CliError` subclasses with a stable `code` and the fixed
  exit-code table (see `core/errors.py`). Don't raise bare exceptions as the
  intended user-facing failure path.
- Any new command that changes external state irreversibly (deletes,
  overwrites a remote resource, restarts something, ...) must support
  `--dry-run` (`output.is_dry_run`) and gate the actual action behind
  `output.require_confirmation`. Commands that only touch local project
  files (`init`, `config set`) don't need this.

## Library API (other projects depend on it)

`gsc` is imported as a library (spider, …) — everything in `gsc.__all__`
(`SearchConsole`, `PageSpeed`, the models, `NotAuthorized` / `PropertyNotFound`
/ `QuotaExceeded` / `ApiError`, `auth_status`, `default_range`, `property_for`,
`parse_*`) is the public contract: renaming a field or changing a signature is
a **major** release. Rules:

- `import gsc` must stay free of side effects: no network, no keychain read, no
  `typer` / `google.auth` import (a test checks this in a subprocess). Clients
  read credentials lazily, on the first request.
- Parsing lives in `core/search_console.py` / `core/pagespeed.py` (`parse_*`),
  models in `core/models.py`; commands only render models.
- `tests/fixtures/psi_ost_term_mobile.json` is a real (trimmed) PSI response —
  refresh it when Lighthouse changes its format, don't hand-edit its structure.
- `gsc.testing.FakeSearchConsole` / `FakePageSpeed` / `FakeCrUX` must keep the exact public
  method signatures of the real clients — `test_fakes_mirror_real_api` fails
  otherwise. Add a method to both.
- Quotas are handled here, not by callers: `core/quota.py` (`RateLimiter`,
  `InspectionQuota` — local daily counter in the user state dir).
- Credentials come from the shared package **google-oauth** (sibling repo
  `../google-oauth`, the Google counterpart of yandex-oauth). `core/auth.py`
  holds gsc's `Profile` + `GOOGLE_AUTH` and thin wrappers that keep the public
  API; `commands/auth.py` is `make_auth_app(GOOGLE_AUTH, output)`;
  `credentials/manager.py` re-exports the store (and `keyring` as the test patch
  target); `CliError` / `InvalidArguments` / `NotAuthorized` are imported from
  `google_oauth.errors` so `output.guard` catches shared errors. Keychain slot is
  shared by all Google tools: `google-oauth:service_account` / `default` and
  `google-oauth:api_key` / `pagespeed`. Env (gsc names first, then shared
  `GOOGLE_OAUTH_*`) overrides keychain. No `.env`. Change key lookup/storage in
  google-oauth, not here.

## Releasing

Never edit `version =` in `pyproject.toml` by hand. Add a line under
`## [Unreleased]` in `CHANGELOG.md` with each change, and when it should
ship run `uv run scripts/release.py patch|minor|major` from a clean
`main` — it bumps the version, dates the changelog, commits, tags
`v<version>` and pushes. Projects pin the CLI they need via
`[cli] min_version` in their config, so a change a project depends on
needs a release before that project can require it.

## After changing the command surface

Nothing to update by hand: agents discover commands from a bare
`gsc` / `--help`, which is rendered from the command
docstrings — so the docstring *is* the API doc, keep it accurate (the
pre-commit hook warns when it drifts). `src/gsc/data/SKILL.md`
deliberately lists no commands, only conventions; touch it only if a
convention changes (a new exit code, a new credential rule).
