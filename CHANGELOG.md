# Changelog

All notable changes to this project are documented here. The format is
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/). `scripts/release.py` moves the Unreleased
section under a new version heading — add entries here as you go, don't
write them at release time.

## [Unreleased]

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

- Доступы — только связка ключей ОС (`gsc:google`, `gsc:pagespeed`) и переменные
  окружения: `gsc auth login --file key.json`, `gsc auth login --provider pagespeed`.
  Старые переменные `GOOGLE_SERVICE_ACCOUNT_*` и `GOOGLE_PAGESPEED_API_KEY` работают.
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
