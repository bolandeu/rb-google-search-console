# gsc — Google Search Console и PageSpeed Insights

Данные [Search Console](https://search.google.com/search-console) (ресурсы, поисковая
аналитика, инспекция URL, карты сайта) и [PageSpeed Insights](https://pagespeed.web.dev/)
(Lighthouse, CrUX, все аудиты). Работает как CLI (`gsc analytics …`) и как Python-библиотека
(`import gsc`). Пакет, импорт и команда — `gsc`. Поддерживаются macOS и Linux.

## Установка

```bash
uv tool install "git+https://github.com/bolandeu/google-search-console.git"
```

Обновление — `uv tool upgrade gsc`, конкретная версия — `...google-search-console.git@v0.2.0`.

**Репозиторий приватный.** `uv` ходит в git так же, как `git clone`. Если установка падает
с ошибкой авторизации — один раз `gh auth login` (или `gh auth setup-git`, если `gh`
залогинен через `--with-token`), либо SSH-вариант:

```bash
uv tool install "git+ssh://git@github.com/bolandeu/google-search-console.git"
```

Как зависимость другого проекта (библиотека):
`uv add "gsc @ git+https://github.com/bolandeu/google-search-console.git"`.

## Доступы

Секреты живут только в связке ключей ОС (Keychain) и переменных окружения; `.env` не читается.

**Search Console — сервисный аккаунт Google.**

1. [Google Cloud Console](https://console.cloud.google.com/iam-admin/serviceaccounts) →
   создать сервисный аккаунт → *Keys → Add key → JSON*; включить *Google Search Console API*.
2. `gsc auth login --file ~/Downloads/key.json` — JSON ключа кладётся в Keychain (`gsc:google`),
   файл после этого можно удалить.
3. Email аккаунта (выводится командой) добавить в Search Console → *Настройки → Пользователи
   и разрешения* каждого нужного ресурса. Для `submit-sitemap` — с полными правами.

Порядок поиска ключа: `GSC_GOOGLE_SERVICE_ACCOUNT_JSON` → `GOOGLE_SERVICE_ACCOUNT_JSON` →
`GOOGLE_SERVICE_ACCOUNT_FILE` (путь к файлу) → Keychain.

**PageSpeed Insights — API-ключ** (без ключа квота Google нулевая).

1. Cloud Console → *APIs & Services → Library* → включить *PageSpeed Insights API*.
2. *Credentials → Create credentials → API key*; желательно ограничить ключ этим API.
3. `gsc auth login --provider pagespeed` (спросит скрытым вводом) или env `GSC_PAGESPEED_API_KEY`
   (старое имя `GOOGLE_PAGESPEED_API_KEY` тоже работает).

```bash
gsc auth status          # что найдено; --check — ещё и спросить у Google, принят ли ключ
gsc doctor               # общая диагностика
```

## CLI

```bash
gsc                                   # версия + список команд
gsc analytics --help                  # опции и формат --json
gsc --ai                              # памятка для AI-агентов
```

```bash
gsc sites                                              # ресурсы аккаунта
gsc sites --for https://blog.example.com/post          # какой ресурс покрывает URL
gsc analytics -s sc-domain:example.com -d page,query --limit 100
gsc inspect -s sc-domain:example.com https://example.com/a https://example.com/b
gsc sitemaps -s sc-domain:example.com
gsc submit-sitemap -s sc-domain:example.com https://example.com/sitemap.xml --dry-run
gsc pagespeed https://example.com --strategy desktop -c performance,seo --audits
```

`--json` у каждой команды; коды выхода: 0 успех, 2 неверные аргументы / нет доступа к
ресурсу, 3 нужны доступы, 5 сбой API Google (в т. ч. квота), 6 CLI устарел.

В папке проекта ресурс можно закрепить: `gsc init --site sc-domain:example.com` — тогда
`-s` не нужен (`.gsc/config.toml`, секретов там нет).

## Библиотека

Публичный API — всё из `gsc.__all__`; меняется только по SemVer. Импорт не лезет в сеть,
keychain и CLI; ключ читается при первом запросе. Всё синхронное.

```python
import gsc

sc = gsc.SearchConsole()
site = sc.property_for("https://example.com/")  # доменный ресурс важнее URL-prefix
start, end = gsc.default_range()  # 28 дней с задержкой данных 3 дня

for row in sc.iter_search_analytics(site, start, end, dimensions=["page", "query"]):
    row.keys["page"], row.clicks, row.impressions, row.ctr, row.position  # постранично по 25 000

for item in sc.inspect_many(urls, site, limit=500):  # темп 600/мин, стоп на дневной квоте
    if isinstance(item, gsc.InspectionError):
        ...
    else:
        item.coverage_state, item.google_canonical, item.rich_results

ps = gsc.PageSpeed()
r = ps.analyze("https://example.com/", "mobile", ["performance", "seo"])
r.scores, r.lab.lcp_ms, r.crux_url, r.crux_origin, r.crux_origin_fallback, r.audit("render-blocking-resources")
for res in ps.analyze_many(urls, "mobile", concurrency=4):
    ...

gsc.auth_status()  # AuthStatus(google="ok"|"missing"|"expired", pagespeed_key=bool, account=…)
```

| Ошибка | Когда | Что делать |
| --- | --- | --- |
| `gsc.NotAuthorized` | нет ключа / Google его отверг | `.action` — команда `gsc auth login …` |
| `gsc.PropertyNotFound` | ресурса нет или нет доступа | добавить email аккаунта в Search Console |
| `gsc.QuotaExceeded` | квота API; `.daily`, `.retry_after` (с) | ждать `retry_after` |
| `gsc.ApiError` | сеть, 5xx, прочие 4xx после повторов; `.status` | повторить позже |

Все они — подклассы `gsc.CliError` (`.code`, `.message`, `.action`). Ошибки по отдельным URL в
`inspect_many` / `analyze_many` не прерывают обход — приходят как `InspectionError` /
`PageSpeedError`.

**Тесты без сети:** `gsc.testing.FakeSearchConsole` / `FakePageSpeed` — те же методы, данные
задаются моделями (`gsc.Row`, `gsc.Inspection`, `gsc.PageSpeedResult`), исключение в словаре —
ошибка по этому URL. Разобрать записанный ответ API: `gsc.parse_inspection`, `gsc.parse_pagespeed`.

**Квота URL Inspection** учитывается локально (файл в папке состояния пользователя, общий для
процессов на машине): `sc.quota_remaining(site)`. Запросы с других машин он не видит — это оценка;
точный стоп даёт ответ Google 429.

## Разработка

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest
scripts/install_hooks.sh   # pre-commit предупреждает об устаревших docstring команд (это их --help)
uv run scripts/release.py minor   # релиз: версия, CHANGELOG, тег, push
```

Архитектура — шаблон [cli-generator](https://github.com/bolandeu/cli-generator); правила для
агентов-разработчиков — [AGENTS.md](AGENTS.md).

### Выбор решений

- **HTTP к Google — `httpx` через общий `HttpProvider`**, токен сервисного аккаунта —
  `google-auth`. `google-api-python-client` убран: тяжёлый (discovery, httplib2), свои
  повторы и исключения, хуже тестируется; нужные эндпоинты (webmasters/v3, urlInspection v1,
  PSI v5) — пять REST-вызовов.
- **Сервисный аккаунт, а не OAuth пользователя** — работает неинтерактивно везде (CI, spider);
  цена — добавлять email аккаунта в каждый ресурс.
- **MCP-сервер удалён** — агенты вызывают CLI с `--json` по памятке `gsc --ai`.
