# rb-google-search-console

Google Search Console + PageSpeed Insights — библиотека, CLI и MCP-сервер.

## Установка

```bash
# Как библиотеку (editable)
uv add --editable ~/Projects/_shared/libs/rb-google-search-console

# Глобальная CLI
uv tool install ~/Projects/_shared/libs/rb-google-search-console
```

## Credentials

### Service Account (основной способ)

1. Создайте service account в [Google Cloud Console](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Скачайте JSON-ключ
3. Добавьте service account email в Google Search Console → Настройки → Пользователи и разрешения
4. Задайте переменную:

```bash
export GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
```

### PageSpeed API Key (опционально)

```bash
export GOOGLE_PAGESPEED_API_KEY=your-api-key
```

Без ключа PageSpeed работает, но с ограниченными лимитами.

## Использование

### Как библиотеку

```python
from rb_gsc import GSCClient, PageSpeedClient

# Search Console
client = GSCClient()
sites = client.list_sites()

result = client.search_analytics_query(
    site_url="sc-domain:example.com",
    dimensions=["query", "page"],
    start_date="2024-01-01",
    end_date="2024-01-31",
)
for row in result.rows:
    print(f"{row.keys}: {row.clicks} clicks, pos {row.position:.1f}")

# URL Inspection
inspection = client.inspect_url("https://example.com/page", "sc-domain:example.com")
print(f"Index: {inspection.verdict}, Coverage: {inspection.coverage_state}")

# Sitemaps
sitemaps = client.list_sitemaps("sc-domain:example.com")

# PageSpeed
ps = PageSpeedClient()
result = ps.analyze_url("https://example.com", strategy="mobile", categories=["performance", "seo"])
print(f"Score: {result.overall_score * 100:.0f}")
```

### CLI

```bash
rb-gsc sites
rb-gsc analytics -s sc-domain:example.com -d query --limit 50
rb-gsc inspect -s sc-domain:example.com https://example.com/page
rb-gsc sitemaps -s sc-domain:example.com
rb-gsc submit-sitemap -s sc-domain:example.com https://example.com/sitemap.xml
rb-gsc pagespeed https://example.com --strategy desktop -c performance,seo
```

### MCP-сервер

```bash
rb-gsc mcp
```

Или в `.mcp.json`:

```json
{
  "mcpServers": {
    "rb-google-search-console": {
      "type": "stdio",
      "command": "sh",
      "args": ["-c", "uv run --project ~/Projects/_shared/libs/rb-google-search-console rb-gsc mcp"]
    }
  }
}
```
