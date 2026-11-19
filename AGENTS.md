# AGENTS.md

Pointers for agents. Antagor shows the changing state (statuses, branches, tasks): `antagor board`.

- What the project is, and the domain glossary: `CONTEXT.md`. Take terms only from there.
- Decisions and why: `docs/adr/` (format: `docs/adr/README.md`).
- Code rules for review: `CODING_STANDARDS.md`.
- Antagor keeps the tasks and epics: `.agents/antagor/`.
- How to write to the Human and to agents (ASD-STE100): the skill `antagor-method`, section «How to write to the Human and to agents».
- The package Standard: https://homeserver.tailee01ab.ts.net:3000/bolandeu/cli-generator/src/branch/main/skills/cli-builder/reference/standard.md (sections by name, for example «Install»).
- The gate before a commit: `gate check`, on this machine — the command is `[publish] gate_command` in `.agents/antagor/antagor.toml` (Standard, CI). It is the only gate: no workflow runs it.

## Development

```bash
uv sync                          # also writes uv.lock — commit it (the gate runs `uv lock --check`)
uv run gsc --help
```

Distribution name is `rb-google-search-console` (`_distribution.DIST_NAME`);
the command and the import package stay `gsc`. `DIST_NAME_LEGACY = "gsc"` lets an
install made under the old name still report its version. In an old dev venv run
`uv sync --reinstall-package rb-google-search-console` once — otherwise the rename
removes `.venv/bin/gsc` and `uv run gsc` silently runs another `gsc` from PATH.

After changing any help text: `uv run pytest --snapshot-update` and review
`tests/snapshots/help/`. `src/gsc/data/SKILL.md` deliberately lists no commands, only
conventions; touch it only if a convention changes (a new exit code, a new credential rule).

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
  `google_oauth`, from the Gitea registry via `[tool.uv.sources]`; sibling repo
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

## Inside the tools system

This tool is one service among many; the root `~/Work/tools/` agent
deploys it, keeps its credentials (Doppler) and backs up its data (S3).
Full rules: `~/Work/tools/docs/standard-release.md` §13.

- **Report to the root agent** (in the report to the user, next to the
  release tag): a new or renamed env var / credential, a new local database
  or changed data path, a new or dropped dependency on another tool, a
  refreshed token written back locally, a breaking release.
- **Consumers**: before a breaking change, check who uses this tool (root
  `AGENTS.md` → Service map) and name them in the report.
- **Headless Linux servers**: env vars first, keychain optional (a missing
  keychain is not an error when the env var is set); reuse existing env var
  names; no prompts without a TTY; no Mac-only paths.
- **Local data** lives in `platformdirs.user_data_dir("<tool>")`, never in
  the repo; all state in the database file, migrations run by the tool; the
  tool never uploads or syncs its data itself.

## Architect only

A worker does not need this section: Antagor cuts it from the worker's brief.
