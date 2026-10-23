# gsc — Google Search Console, PageSpeed Insights и CrUX

Данные [Search Console](https://search.google.com/search-console) (ресурсы, поисковая
аналитика, инспекция URL, карты сайта), [PageSpeed Insights](https://pagespeed.web.dev/)
(Lighthouse, CrUX, все аудиты) и [Chrome UX Report API](https://developer.chrome.com/docs/crux/api)
(реальные посетители Chrome, история по неделям). Работает как CLI (`gsc analytics …`) и как Python-библиотека
(`import gsc`). Пакет, импорт и команда — `gsc`. Поддерживаются macOS и Linux.

## Установка

Из реестра Gitea (пакет выпускается туда):

```bash
uv tool install rb-google-search-console --index https://homeserver.tailee01ab.ts.net:3000/api/packages/bolandeu/pypi/simple
```

Или из git-тега, на любой другой машине:

```bash
uv tool install "rb-google-search-console @ git+https://homeserver.tailee01ab.ts.net:3000/bolandeu/google-search-console.git@vX.Y.Z"
```

`vX.Y.Z` — последний тег релиза (ставить из тега, не из ветки). Обновление — `uv tool upgrade rb-google-search-console`.
Дистрибутив называется `rb-google-search-console` (`gsc` на PyPI — чужой пакет), команда и импорт — `gsc`.
Стоит старая установка под именем `gsc` — сначала `uv tool uninstall gsc`, иначе два
инструмента делят одну команду.

Как зависимость другого проекта (библиотека): `"rb-google-search-console>=0.5,<0.6"` в `dependencies` и
`rb-google-search-console = { index = "gitea" }` в `[tool.uv.sources]` (с индексом `gitea` из `[[tool.uv.index]]`).

## Доступы

Секреты живут только в связке ключей ОС (Keychain) и переменных окружения; `.env` не читается.

**Search Console — сервисный аккаунт Google.**

1. [Google Cloud Console](https://console.cloud.google.com/iam-admin/serviceaccounts) →
   создать сервисный аккаунт → *Keys → Add key → JSON*; включить *Google Search Console API*.
2. `gsc auth login --file ~/Downloads/key.json` — JSON ключа кладётся в Keychain, в общий слот
   всех Google-инструментов (`google-oauth:service_account`, пакет
   [google-oauth](https://homeserver.tailee01ab.ts.net:3000/bolandeu/google-oauth)); файл после этого можно удалить.
3. Email аккаунта (выводится командой) добавить в Search Console → *Настройки → Пользователи
   и разрешения* каждого нужного ресурса. Для `submit-sitemap` — с полными правами.

Порядок поиска ключа: `GSC_GOOGLE_SERVICE_ACCOUNT_JSON` → `GOOGLE_SERVICE_ACCOUNT_JSON` →
`GOOGLE_OAUTH_SERVICE_ACCOUNT_JSON` → `GOOGLE_SERVICE_ACCOUNT_FILE` / `GOOGLE_OAUTH_SERVICE_ACCOUNT_FILE`
(путь к файлу) → Keychain. Вход общий: ключ, положенный другим Google-инструментом, gsc тоже видит,
а `gsc auth logout` удаляет его для всех.

**PageSpeed Insights — API-ключ** (без ключа квота Google нулевая).

1. Cloud Console → *APIs & Services → Library* → включить *PageSpeed Insights API*.
2. *Credentials → Create credentials → API key*; желательно ограничить ключ этим API.
3. `gsc auth login --provider pagespeed` (спросит скрытым вводом; Keychain `google-oauth:api_key`)
   или env `GSC_PAGESPEED_API_KEY` (а также `GOOGLE_PAGESPEED_API_KEY`, `GOOGLE_OAUTH_PAGESPEED_API_KEY`).
4. Для `gsc crux` тот же ключ: включить **Chrome UX Report API** и добавить его в ограничения ключа
   (в списке ограничений видны только уже включённые API). Изменения доходят за 1–5 минут.

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
gsc analytics -s sc-domain:example.com -d page,query --by-day --limit 0 --json > full.json   # без предела 50 000
gsc analytics -s sc-domain:example.com -d query -f page:contains:/blog/ --aggregation byPage
gsc inspect -s sc-domain:example.com https://example.com/a https://example.com/b
gsc sitemaps -s sc-domain:example.com
gsc submit-sitemap -s sc-domain:example.com https://example.com/sitemap.xml --dry-run
gsc pagespeed https://example.com --strategy desktop --audits          # все 4 категории
gsc crux --origin https://example.com --form-factor phone               # реальные посетители, 28 дней
gsc crux --origin https://example.com --history --periods 40            # тренд по неделям
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

rows = sc.iter_search_analytics(
    site,
    start,
    end,
    dimensions=["page", "query"],
    filters=[{"dimension": "page", "operator": "contains", "expression": "/blog/"}],
    aggregation_type="byPage",  # byPage / byProperty считают клики и показы по-разному
    by_day=True,  # по запросу на день: обходит предел ~50 000 строк на запрос
)
for row in rows:  # постранично по 25 000
    row.keys["page"], row.keys["date"], row.clicks, row.impressions, row.ctr, row.position
rows.first_incomplete_date  # при data_state="all": с какой даты данные неполные

for item in sc.inspect_many(urls, site, limit=500):  # темп 600/мин, стоп на дневной квоте
    if isinstance(item, gsc.InspectionError):
        ...
    else:
        item.coverage_state, item.google_canonical, item.rich_results

ps = gsc.PageSpeed()
r = ps.analyze("https://example.com/", "mobile")  # все 4 категории за одну единицу квоты
r.scores, r.lab.lcp_ms, r.crux_origin.lcp.good, r.crux_origin_fallback
a = r.audit("render-blocking-insight")
a.description, a.categories, a.details, a.metric_savings  # категория, вес, группа; советы
r.stack_packs, r.entities, r.run_warnings, r.runtime_error  # платформа, сторонние сервисы, сбои замера
for res in ps.analyze_many(urls, "mobile", concurrency=4):
    ...

crux = gsc.CrUX()  # тот же ключ; нет данных у Google → None
crux.record(origin="https://example.com", form_factor="PHONE").metrics["largest_contentful_paint"]
crux.history("https://example.com/", periods=40).metrics["largest_contentful_paint"].p75  # по неделям

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

**Тесты без сети:** `gsc.testing.FakeSearchConsole` / `FakePageSpeed` / `FakeCrUX` — те же методы, данные
задаются моделями (`gsc.Row`, `gsc.Inspection`, `gsc.PageSpeedResult`), исключение в словаре —
ошибка по этому URL. Разобрать записанный ответ API: `gsc.parse_inspection`, `gsc.parse_pagespeed`,
`gsc.parse_crux_record`, `gsc.parse_crux_history`.

**Чего нет ни в одном API** (только интерфейс Search Console): сводный отчёт об индексировании,
отчёт Core Web Vitals, ссылки, ручные меры, безопасность, статистика сканирования. Полные данные
поиска без предела строк — только [выгрузка в BigQuery](https://support.google.com/webmasters/answer/12918484)
(настраивается в интерфейсе GSC).

**Квота URL Inspection** учитывается локально (файл в папке состояния пользователя, общий для
процессов на машине): `sc.quota_remaining(site)`. Запросы с других машин он не видит — это оценка;
точный стоп даёт ответ Google 429.

## Разработка

```bash
uv sync
uv run gsc --help
uv run pytest --snapshot-update     # после изменения справки команды — снапшоты tests/snapshots/help/
```

Гейт — шаг `rb-release check` в `.gitea/workflows/ci.yml`: его команду запускают перед каждым коммитом.
Версия — git-тег (`vX.Y.Z`); работа и релизы идут через Antagor. Архитектура — шаблон
[cli-generator](https://homeserver.tailee01ab.ts.net:3000/bolandeu/cli-generator); правила для
агентов-разработчиков — [AGENTS.md](AGENTS.md).

### Выбор решений

- **HTTP к Google — `httpx` через общий `HttpProvider`**, токен сервисного аккаунта —
  `google-auth`. `google-api-python-client` убран: тяжёлый (discovery, httplib2), свои
  повторы и исключения, хуже тестируется; нужные эндпоинты (webmasters/v3, urlInspection v1,
  PSI v5) — пять REST-вызовов.
- **Сервисный аккаунт, а не OAuth пользователя** — работает неинтерактивно везде (CI, spider);
  цена — добавлять email аккаунта в каждый ресурс.
- **MCP-сервер удалён** — агенты вызывают CLI с `--json` по памятке `gsc --ai`.
