# AGENTS.md

Guidance for coding agents working on the **gsc** package
itself (not its end users — see `src/gsc/data/SKILL.md` for
that).

## Development

```bash
uv sync                          # also writes uv.lock — commit it (the gate runs `uv lock --check`)
uv run gsc --help
uv run scripts/release.py --check
```

Before calling anything done, `release.py --check` must pass — it is the
authoritative gate (tools/docs/standard-release.md §3): lock, ruff, ty, pytest
(incl. the `--help` contract and snapshots, the `auth status` shape), the
`[[tool.rb.external]]` check, a changelog fragment, a wheel build + install +
`gsc --version`, osv-scanner. There is no GitHub CI: rb-google-oauth is a
private dependency and the repo has no read-token secret (standard §9).

Run `scripts/install_hooks.sh` once (`core.hooksPath` → `.githooks/`; the
Claude Code SessionStart hook does it too). The pre-commit hook **blocks** a
commit where a command's logic changed without its docstring (the `--help`
text agents read as this CLI's API contract), and warns when `src/` changed
without a changelog fragment. After changing any help text:
`uv run pytest --snapshot-update` and review `tests/snapshots/help/`.

Distribution name is `rb-google-search-console` (`_distribution.DIST_NAME`,
standard §10); the command and the import package stay `gsc`.
`DIST_NAME_LEGACY = "gsc"` lets an install made under the old name still
report its version. In an old dev venv run `uv sync --reinstall-package
rb-google-search-console` once — otherwise the rename removes `.venv/bin/gsc`
and `uv run gsc` silently runs another `gsc` from PATH.

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
- Credentials come from the shared package **rb-google-oauth** (import
  `google_oauth`, pinned to a release tag in `[tool.uv.sources]`; sibling repo
  `../google-oauth`, the Google counterpart of yandex-oauth). `core/auth.py`
  holds gsc's `Profile` + `GOOGLE_AUTH` and thin wrappers that keep the public
  API; `commands/auth.py` is `make_auth_app(GOOGLE_AUTH, output, check=…, api_key_checks=…)`
  — `auth status [--check] --json` is the standard §8 report (shape tested in
  `tests/test_auth.py`; changing it is a breaking change); `--check` probes
  `sites` with the service account and CrUX `queryRecord` with the PSI key
  (PSI itself runs Lighthouse for 10–60 s);
  `credentials/manager.py` re-exports the store (and `keyring` as the test patch
  target); `CliError` / `InvalidArguments` / `NotAuthorized` are imported from
  `google_oauth.errors` so `output.guard` catches shared errors. Keychain slot is
  shared by all Google tools: `google-oauth:service_account` / `default` and
  `google-oauth:api_key` / `pagespeed`. Env (gsc names first, then shared
  `GOOGLE_OAUTH_*`) overrides keychain. No `.env`. Change key lookup/storage in
  google-oauth, not here.

## Releasing

Version comes from the git tag (`vX.Y.Z`, uv-dynamic-versioning) — there is
no `version =` line. Never edit `CHANGELOG.md` between releases: each change
with a user-visible effect adds a fragment
(`uv run towncrier create +<slug>.<type>.md -c "…"`, types: added, changed,
deprecated, removed, fixed, security). Release from a clean, pushed `main`:
`uv run scripts/release.py patch|minor|major` (at 0.x: patch — fixes and
features, minor — anything breaking on the public surface) runs the gate,
assembles the changelog, commits and tags; push with `git push --follow-tags`.
Projects pin the CLI they need via `[cli] min_version` in their config, so a
change a project depends on needs a release before that project can require it.

## After changing the command surface

Nothing to update by hand: agents discover commands from a bare
`gsc` / `--help`, which is rendered from the command
docstrings — so the docstring *is* the API doc, keep it accurate (the
pre-commit hook warns when it drifts). `src/gsc/data/SKILL.md`
deliberately lists no commands, only conventions; touch it only if a
convention changes (a new exit code, a new credential rule).
