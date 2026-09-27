# CLAUDE.md

## Commands

```bash
# Install dependencies (editable mode)
uv sync --all-extras

# Run CLI
uv run rb-gsc sites
uv run rb-gsc analytics -s sc-domain:example.com -d query,page
uv run rb-gsc inspect -s sc-domain:example.com https://example.com/page
uv run rb-gsc sitemaps -s sc-domain:example.com
uv run rb-gsc pagespeed https://example.com --strategy mobile

# Run tests
uv run pytest

# Run MCP server (stdio)
uv run rb-gsc mcp
```

## Architecture

**Three usage modes:** Python library, CLI (`rb-gsc`), MCP server (`rb-gsc mcp`).

**Source layout:** `src/rb_gsc/`

- `core/models.py` — Pydantic-модели: Site, SearchAnalyticsParams/Result/Row, UrlInspectionResult, Sitemap, PageSpeedParams/Result/Metrics
- `core/auth.py` — аутентификация: service account (JSON file / env) и OAuth2 flow
- `core/client.py` — `GSCClient`: sites, search analytics, URL inspection, sitemaps
- `core/pagespeed.py` — `PageSpeedClient`: PageSpeed Insights API v5
- `cli.py` — Click CLI; команды: sites, analytics, inspect, sitemaps, submit-sitemap, pagespeed, mcp
- `mcp_server.py` — MCP-сервер с 6 инструментами; логи в `~/.local/state/logs/mcp-rb-gsc.log`

**API:**
- Search Console: `webmasters/v3` + `searchconsole/v1` (через google-api-python-client)
- PageSpeed Insights: `https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed`

**Credentials:**
- `GOOGLE_SERVICE_ACCOUNT_FILE` — путь к service account JSON
- `GOOGLE_SERVICE_ACCOUNT_JSON` — JSON-строка service account (для Docker)
- `GOOGLE_PAGESPEED_API_KEY` — API ключ для PageSpeed (опционально, увеличивает лимиты)

**MCP tools:** `gsc_list_sites`, `gsc_search_analytics`, `gsc_inspect_url`, `gsc_list_sitemaps`, `gsc_submit_sitemap`, `pagespeed_analyze`.
