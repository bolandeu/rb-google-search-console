# Changelog

All notable changes to this project are documented here. The format is
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/). Don't edit this file between releases: each
change adds a fragment to `changelog.d/`
(`uv run towncrier create +<slug>.<type>.md -c "…"`), and
`scripts/release.py` assembles them here.

<!-- towncrier release notes start -->

## [0.4.0] - 2026-09-28

### Changed

- **Ломающее.** `gsc auth status [--check] --json` выдаёт отчёт §8 стандарта tools (`tool`, `version`, `checked_at`, `credentials[]` — записи `google` и `pagespeed` с `status`, `source`, `source_ref`, …) вместо плоского `{google, pagespeed_key, account, source, detail}`; нет ключа сервисного аккаунта или ключ негоден — exit 3, `ok: false` и `error` `CREDENTIALS_UNHEALTHY` рядом с отчётом. `--check` проверяет сервисный аккаунт списком ресурсов, а API-ключ PageSpeed — запросом к Chrome UX Report (не дольше 10 с на ключ). Авторизация — `rb-google-oauth` v0.2.0 (пин на тег). Библиотечные `gsc.auth_status()` / `gsc.AuthStatus` не менялись.
- **Ломающее.** Дистрибутив переименован: `gsc` → `rb-google-search-console` (стандарт tools §10: `gsc` на PyPI — чужой пакет); команда `gsc` и импорт `gsc` не меняются. Потребителям: новое имя в `dependencies` и ключ `[tool.uv.sources]` с пином на тег (`rb-google-search-console = { git = "https://github.com/bolandeu/google-search-console.git", tag = "v0.4.0" }`), в существующем venv — `uv sync --reinstall-package rb-google-search-console`; установленный инструмент — `uv tool uninstall gsc`, затем `uv tool install "rb-google-search-console @ git+https://github.com/bolandeu/google-search-console.git@v0.4.0"`. Установка под старым именем по-прежнему сообщает свою версию.
- Стандарт релизов tools: версия из git-тега, changelog из фрагментов `changelog.d/`, `scripts/release.py` и хуки из шаблона cli-generator v1.2.10; в `--help` каждой команды — строка `Example:`, текст в квадратных скобках больше не пропадает из справки. `CLI_TOO_OLD` подсказывает `uv tool upgrade rb-google-search-console`; сборка без тега (`0.0.0…`) не проверяется против `cli.min_version`.


## [0.3.0] - 2026-09-27

### Added

- Search Analytics: `aggregation_type` (`--aggregation byPage|byProperty`), `by_day`
  (`--by-day` — запрос на каждый день, обходит предел Google ~50 000 строк на запрос),
  фильтры в CLI (`--filter СРЕЗ:ОПЕРАТОР:ВЫРАЖЕНИЕ`), почасовые данные (`-d hour
  --data-state hourly_all`), `first_incomplete_date` — с какой даты данные неполные
  (`iter_search_analytics` возвращает `SearchAnalyticsRows` — по-прежнему итератор `Row`).
- Карты сайта: `contents` — сколько URL каждого типа в карте.
- PageSpeed: все 4 категории по умолчанию (одна единица квоты); доли хороших / средних /
  плохих визитов CrUX; у аудитов — описание, предупреждения, `explanation`, `error_message`,
  категории с весом и группой; `category_titles`, `stack_packs` (советы под WordPress и др.),
  `entities` (сторонние сервисы), `run_warnings`, `runtime_error`; скриншоты только по
  `screenshots=True` / `--screenshots` (иначе base64-картинки из деталей выбрасываются).
- Chrome UX Report API: `gsc.CrUX` (`record`, `history` до 40 недель), команда `gsc crux`,
  `parse_crux_record` / `parse_crux_history`, `gsc.testing.FakeCrUX`. Ключ — тот же, что у
  PageSpeed, с включённым Chrome UX Report API.

## [0.2.0] - 2026-09-27

Пакет переименован: `rb-google-search-console` / `rb_gsc` / команда `rb-gsc` →
**`gsc`** (дистрибутив, импорт и команда). Переведён на архитектуру cli-generator.

### Added

- Публичный API библиотеки (`import gsc`, без побочных эффектов при импорте):
  `SearchConsole` (`list_properties`, `get_property`, `property_for`,
  `iter_search_analytics` с постраничной выдачей по 25 000, `inspect_url`,
  `inspect_many` с темпом 600/мин и стопом на дневной квоте, `quota_remaining`,
  карты сайта), `PageSpeed` (`analyze`, `analyze_many` с параллелизмом и лимитом
  400/100 с), `auth_status()`, `default_range()`, `property_for()`,
  `parse_inspection` / `parse_pagespeed`; типизированные ошибки `NotAuthorized`,
  `PropertyNotFound`, `QuotaExceeded(retry_after, daily)`, `ApiError`.
- URL Inspection: canonical Google и сайта, карты сайта, мобильность, AMP,
  расширенные результаты с issues, исходный ответ в `raw`.
- PageSpeed: CrUX по URL и по origin (LCP, INP, CLS, FCP, TTFB — percentile и
  category), признак `crux_origin_fallback`, все аудиты Lighthouse (details,
  savings, metricSavings), версия Lighthouse.
- `gsc.testing.FakeSearchConsole` / `FakePageSpeed` — клиенты для тестов без сети.
- CLI: `--json` у всех команд, коды выхода и конверт ошибок cli-generator;
  `sites --for URL`; `inspect` и `pagespeed` принимают несколько URL;
  `submit-sitemap --dry-run`; `doctor`, `status`, `init --site`, `config`,
  `auth login|logout|status [--check]`, `skill install`, `--ai`; справка на русском.
- Локальный учёт дневной квоты URL Inspection (папка состояния пользователя).

### Changed

- Доступы — только связка ключей ОС и переменные окружения:
  `gsc auth login --file key.json`, `gsc auth login --provider pagespeed`.
  Старые переменные `GOOGLE_SERVICE_ACCOUNT_*` и `GOOGLE_PAGESPEED_API_KEY` работают.
- Авторизация вынесена в общий пакет **google-oauth** (как yandex-oauth у Яндекс-инструментов):
  ключи лежат в общем слоте keychain всех Google-инструментов —
  `google-oauth:service_account` / `default` (JSON ключа сервисного аккаунта) и
  `google-oauth:api_key` / `pagespeed`; вход в одном инструменте авторизует остальные,
  `gsc auth logout` выходит из всех. Записи `gsc:google` / `gsc:pagespeed` больше не
  читаются — перенесите ключ заново: `gsc auth login --file key.json`.
  Добавлены общие переменные `GOOGLE_OAUTH_SERVICE_ACCOUNT_JSON` / `_FILE` и
  `GOOGLE_OAUTH_PAGESPEED_API_KEY` (ниже по приоритету, чем переменные gsc).
  Любая переменная окружения с ключом PSI теперь приоритетнее keychain (раньше
  `GOOGLE_PAGESPEED_API_KEY` проверялась после keychain). `gsc.NotAuthorized` теперь
  базовый класс и для `AuthRequired` (401/403 от API) — `except gsc.NotAuthorized`
  ловит оба случая; сигнатуры публичного API не менялись.
- HTTP к Google — `httpx` + `google-auth` вместо `google-api-python-client`;
  ошибки Google больше не выходят трейсбеком.
- `analytics`: период по умолчанию — 28 дней до «сегодня − 3», срез по умолчанию
  `query`, `dataState=final`; `-s` можно не указывать, если ресурс задан в
  `.gsc/config.toml`.
- Результаты `Row.keys` — словарь «срез → значение» вместо списка.

### Removed

- MCP-сервер (`rb-gsc mcp`) и зависимости `mcp`, `click`, `python-dotenv`,
  `loguru`, `google-api-python-client`: агенты вызывают CLI с `--json` по
  памятке `gsc --ai`.
- Чтение `.env` (секреты из файлов больше не берутся).
- `--output/-o` у команд — вместо него `--json > файл`.
- OAuth-вход через браузер (`credentials_from_oauth`) и методы `add_site`,
  `delete_site`, `delete_sitemap` старого `GSCClient` (не использовались).
- Поддержка Windows (CI — Linux и macOS).
