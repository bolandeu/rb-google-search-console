---
name: gsc
description: Данные Google Search Console (ресурсы, поисковая аналитика — клики/показы/CTR/позиции, инспекция URL — индексация, canonical, покрытие; карты сайта) , PageSpeed Insights (Lighthouse, Core Web Vitals, аудиты) и Chrome UX Report (реальные посетители, история по неделям) через CLI `gsc` или Python-библиотеку `gsc`. Использовать, когда задаче нужны данные GSC, статус индексации страниц, скорость сайта (Search Console, GSC, URL inspection, PageSpeed, PSI, Core Web Vitals, CrUX, Lighthouse). Здесь — установка, --json, коды выхода, доступы, квоты.
---

# gsc

Всё про конкретные команды есть в самом CLI: `gsc` без аргументов — версия
и список команд, `gsc <команда> --help` — подробности, формат `--json` и
примеры. Этот документ — только то, чего `--help` не скажет. Если CLI
запускать можно, а файлы читать нельзя, этот же текст печатает `gsc --ai`.

## Установка (если `gsc --version` не работает)

```bash
uv tool install rb-google-search-console --index https://homeserver.tailee01ab.ts.net:3000/api/packages/bolandeu/pypi/simple
```

Или из git-тега:

```bash
uv tool install "rb-google-search-console @ git+https://homeserver.tailee01ab.ts.net:3000/bolandeu/google-search-console.git@vX.Y.Z"
```

`vX.Y.Z` — последний тег релиза (ставить из тега, не из ветки). Обновление —
`uv tool upgrade rb-google-search-console`. Не запускать из исходников, если не просили
разрабатывать сам CLI.

## Правила

- **`--json` у каждой команды.** Разбирать stdout; человеческий вывод не
  парсить. В stdout — только данные, в stderr — диагностика.
- **Ресурс (`-s`)** — ровно как в Search Console: `sc-domain:example.com`
  или `https://example.com/` (со слэшем). Не знаешь ресурс —
  `gsc sites --for <URL> --json` подберёт покрывающий. В папке проекта
  ресурс можно закрепить: `gsc init --site … --non-interactive`, тогда `-s`
  не нужен.
- **Квоты Google, не тратить зря.** URL Inspection — 2000 в сутки и 600 в
  минуту на ресурс; `inspect` сам держит темп и возвращает
  `quota_remaining`. Инспектировать только нужные URL, не весь сайт подряд.
  Кончилась дневная квота — `quota_exhausted: true` (что успели — выводится)
  или `PROVIDER_ERROR` с `daily: true` и `retry_after`; до сброса (полночь
  по тихоокеанскому времени) не повторять. PageSpeed — 25 000 в сутки на ключ.
- **Данные Search Console — с задержкой 2–3 дня**; по умолчанию `analytics`
  берёт 28 дней, заканчивая 3 днями назад. Google отдаёт не больше ~50 000
  строк на запрос — для полного `page,query` на большом сайте `--by-day
  --limit 0` (строки подневные, суммировать самому; позицию — взвешивая по
  показам). Клики по страницам и по сайту считаются по-разному — для
  сравнения явно `--aggregation byPage` или `byProperty`.
- **CrUX** (`gsc crux`) — реальные посетители Chrome, есть только у страниц
  и сайтов с заметным трафиком: `"record": null` — не ошибка, а «данных нет»;
  тогда пробовать `--origin`. Квота 150 запросов в минуту.
- **PageSpeed `--json` большой** (сотни КБ на URL): все аудиты с деталями.
  `runtime_error` не пуст — Lighthouse не смог замерить страницу, цифрам не
  верить. `--screenshots` — только если картинки правда нужны.
- **Доступы** — только keychain ОС или переменные окружения, никогда не в
  аргументах или настройках. Search Console — ключ сервисного аккаунта
  (`gsc auth login --file key.json`, env `GSC_GOOGLE_SERVICE_ACCOUNT_JSON`);
  email аккаунта должен быть добавлен пользователем в Search Console каждого
  ресурса. PageSpeed и CrUX — один API-ключ (`gsc auth login --provider
  pagespeed`, env `GSC_PAGESPEED_API_KEY`); без ключа квота Google нулевая; для
  CrUX в проекте ключа должен быть включён Chrome UX Report API (иначе exit 3
  с подсказкой). Проверка —
  `gsc auth status --json` (exit 3 — обязательного ключа нет или он негоден;
  отчёт в `credentials[]`). Никогда не просить пользователя вставить секрет
  в командную строку.
- **Команды, меняющие состояние в Google** — те, у которых в `--help` есть
  `--dry-run` (сейчас `submit-sitemap`; повторная отправка безвредна). Сначала
  `--dry-run`, показать пользователю, потом без него.
- **`--non-interactive`** для всего, что может задать вопрос: вместо
  зависания будет понятная ошибка.
- **Сначала `gsc doctor --json`**, если что-то не так: проект, настройки,
  совместимость версий, доступы — без сети. Проверить, что Google принимает
  ключ, — `gsc auth status --check --json`.
- **`gsc describe --json`** — весь CLI одним документом OpenCLI (команды, параметры, коды
  выхода, переменные окружения): голый документ, без конверта `{"ok": ...}`.

## Ошибки

Ошибка: `{"ok": false, "error": {"code", "message", "action"}}`.
Порядок: код выхода → `error.code` → `error.action` (конкретная команда,
которая исправит).

    0  успех
    1  прочее (UNEXPECTED — баг: повторить с --verbose и сообщить; ABORTED — пользователь отказался)
    2  неверные аргументы; ресурс не найден / нет доступа (action — кого добавить в Search Console)
    3  нужны доступы              → gsc auth login …
    4  проект не создан           → gsc init
    5  сбой API Google (сеть, 5xx, квота — повторы уже были) → позже; при daily: true — после сброса квоты
    6  CLI старее, чем нужно проекту → uv tool upgrade rb-google-search-console

Автоматически повторять имеет смысл только код 5 без `daily: true`.
