"""MCP-сервер для Google Search Console + PageSpeed Insights."""

from __future__ import annotations

import json

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("rb-google-search-console")
_gsc_client = None
_ps_client = None


def _get_gsc():
    global _gsc_client
    if _gsc_client is None:
        from .core.client import GSCClient
        _gsc_client = GSCClient()
    return _gsc_client


def _get_ps():
    global _ps_client
    if _ps_client is None:
        from .core.pagespeed import PageSpeedClient
        _ps_client = PageSpeedClient()
    return _ps_client


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="gsc_list_sites",
            description="Список всех сайтов в Google Search Console.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="gsc_get_site",
            description="Информация о конкретном сайте в Google Search Console.",
            inputSchema={
                "type": "object",
                "properties": {
                    "site_url": {"type": "string", "description": "URL сайта (sc-domain:example.com)"},
                },
                "required": ["site_url"],
            },
        ),
        Tool(
            name="gsc_search_analytics",
            description=(
                "Поисковая аналитика Google Search Console — клики, показы, CTR, позиции. "
                "Доступные dimensions: query, page, device, country, date, searchAppearance. "
                "Доступные search_type: web, image, video, news, discover, googleNews."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "site_url": {"type": "string", "description": "URL сайта (sc-domain:example.com)"},
                    "start_date": {"type": "string", "description": "Начало YYYY-MM-DD (по умолчанию -30 дней)"},
                    "end_date": {"type": "string", "description": "Конец YYYY-MM-DD (по умолчанию -3 дня)"},
                    "dimensions": {"type": "string", "description": "Срезы через запятую: query,page,device,country,date"},
                    "search_type": {"type": "string", "description": "Тип поиска: web, image, video, news, discover"},
                    "row_limit": {"type": "integer", "description": "Кол-во строк (по умолчанию 25)"},
                },
                "required": ["site_url"],
            },
        ),
        Tool(
            name="gsc_inspect_url",
            description="Инспекция URL в Google Search Console — статус индексации, покрытие, robots.txt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL для инспекции"},
                    "site_url": {"type": "string", "description": "URL сайта (sc-domain:example.com)"},
                },
                "required": ["url", "site_url"],
            },
        ),
        Tool(
            name="gsc_list_sitemaps",
            description="Список карт сайта в Google Search Console.",
            inputSchema={
                "type": "object",
                "properties": {
                    "site_url": {"type": "string", "description": "URL сайта"},
                },
                "required": ["site_url"],
            },
        ),
        Tool(
            name="gsc_get_sitemap",
            description="Информация о конкретной карте сайта в Google Search Console.",
            inputSchema={
                "type": "object",
                "properties": {
                    "site_url": {"type": "string", "description": "URL сайта"},
                    "feedpath": {"type": "string", "description": "URL карты сайта"},
                },
                "required": ["site_url", "feedpath"],
            },
        ),
        Tool(
            name="gsc_submit_sitemap",
            description="Отправить карту сайта на индексацию в Google Search Console.",
            inputSchema={
                "type": "object",
                "properties": {
                    "site_url": {"type": "string", "description": "URL сайта"},
                    "feedpath": {"type": "string", "description": "URL карты сайта"},
                },
                "required": ["site_url", "feedpath"],
            },
        ),
        Tool(
            name="pagespeed_analyze",
            description=(
                "PageSpeed Insights — анализ производительности, доступности, SEO. "
                "Возвращает оценки по категориям и Core Web Vitals (FCP, LCP, TBT, CLS)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL для анализа"},
                    "strategy": {"type": "string", "enum": ["desktop", "mobile"], "description": "Стратегия (по умолчанию mobile)"},
                    "categories": {"type": "string", "description": "Категории: performance,accessibility,best-practices,seo"},
                    "locale": {"type": "string", "description": "Локаль (напр. ru)"},
                },
                "required": ["url"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:

    if name == "gsc_list_sites":
        client = _get_gsc()
        sites = client.list_sites()
        text = "\n".join(f"- {s.site_url} ({s.permission_level})" for s in sites)
        return [TextContent(type="text", text=f"Найдено {len(sites)} сайтов:\n\n{text}")]

    if name == "gsc_get_site":
        client = _get_gsc()
        s = client.get_site(arguments["site_url"])
        return [TextContent(type="text", text=f"{s.site_url}\nДоступ: {s.permission_level}")]

    if name == "gsc_search_analytics":
        client = _get_gsc()
        dims_str = arguments.get("dimensions")
        dims = [d.strip() for d in dims_str.split(",")] if dims_str else None
        result = client.search_analytics_query(
            site_url=arguments["site_url"],
            start_date=arguments.get("start_date"),
            end_date=arguments.get("end_date"),
            dimensions=dims,
            search_type=arguments.get("search_type", "web"),
            row_limit=arguments.get("row_limit", 25),
        )
        lines = []
        for i, row in enumerate(result.rows):
            keys = " | ".join(row.keys) if row.keys else "Итого"
            lines.append(
                f"{i+1}. {keys}: {int(row.clicks)} кликов, "
                f"{int(row.impressions)} показов, "
                f"CTR {row.ctr*100:.1f}%, поз. {row.position:.1f}"
            )
        return [TextContent(type="text", text=f"Поисковая аналитика ({len(result.rows)} строк):\n\n" + "\n".join(lines))]

    if name == "gsc_inspect_url":
        client = _get_gsc()
        r = client.inspect_url(arguments["url"], arguments["site_url"])
        text = (
            f"URL Inspection: {arguments['url']}\n\n"
            f"Verdict: {r.verdict}\n"
            f"Index status: {r.index_status}\n"
            f"Coverage: {r.coverage_state}\n"
            f"Robots.txt: {r.robots_txt_state}\n"
            f"Indexing: {r.indexing_state}\n"
            f"Last crawl: {r.last_crawl_time}\n"
            f"Fetch state: {r.page_fetch_state}\n"
            f"Crawled as: {r.crawled_as}"
        )
        return [TextContent(type="text", text=text)]

    if name == "gsc_list_sitemaps":
        client = _get_gsc()
        sitemaps = client.list_sitemaps(arguments["site_url"])
        if not sitemaps:
            return [TextContent(type="text", text="Карты сайта не найдены.")]
        lines = [
            f"- {s.path} (type: {s.type or '?'}, errors: {s.errors}, warnings: {s.warnings})"
            for s in sitemaps
        ]
        return [TextContent(type="text", text=f"Карты сайта ({len(sitemaps)}):\n\n" + "\n".join(lines))]

    if name == "gsc_get_sitemap":
        client = _get_gsc()
        s = client.get_sitemap(arguments["site_url"], arguments["feedpath"])
        text = (
            f"{s.path}\n"
            f"Type: {s.type or 'N/A'}\n"
            f"Ошибки: {s.errors}\n"
            f"Предупреждения: {s.warnings}\n"
            f"Pending: {s.is_pending}\n"
            f"Sitemaps index: {s.is_sitemaps_index}\n"
            f"Последняя отправка: {s.last_submitted or 'N/A'}\n"
            f"Последняя загрузка: {s.last_downloaded or 'N/A'}"
        )
        return [TextContent(type="text", text=text)]

    if name == "gsc_submit_sitemap":
        from .core.client import GSCClient
        client = GSCClient(readonly=False)
        client.submit_sitemap(arguments["site_url"], arguments["feedpath"])
        return [TextContent(type="text", text=f"Sitemap отправлена: {arguments['feedpath']}")]

    if name == "pagespeed_analyze":
        client = _get_ps()
        cats_str = arguments.get("categories")
        cats = [c.strip() for c in cats_str.split(",")] if cats_str else None
        result = client.analyze_url(
            arguments["url"],
            strategy=arguments.get("strategy", "mobile"),
            categories=cats,
            locale=arguments.get("locale"),
        )
        cat_lines = []
        for c in result.categories:
            score = f"{c.score * 100:.0f}" if c.score is not None else "N/A"
            cat_lines.append(f"  {c.title}: {score}")

        m = result.metrics
        metrics_lines = []
        if m.first_contentful_paint is not None:
            metrics_lines.append(f"  FCP: {m.first_contentful_paint:.0f} ms")
        if m.largest_contentful_paint is not None:
            metrics_lines.append(f"  LCP: {m.largest_contentful_paint:.0f} ms")
        if m.total_blocking_time is not None:
            metrics_lines.append(f"  TBT: {m.total_blocking_time:.0f} ms")
        if m.cumulative_layout_shift is not None:
            metrics_lines.append(f"  CLS: {m.cumulative_layout_shift:.3f}")
        if m.speed_index is not None:
            metrics_lines.append(f"  Speed Index: {m.speed_index:.0f} ms")

        text = (
            f"PageSpeed: {result.url} ({result.strategy})\n\n"
            f"Категории:\n" + "\n".join(cat_lines) + "\n\n"
            f"Метрики:\n" + "\n".join(metrics_lines)
        )
        return [TextContent(type="text", text=text)]

    raise ValueError(f"Неизвестный инструмент: {name}")


def serve() -> None:
    """Entry-point для MCP-сервера."""
    import asyncio
    from pathlib import Path

    from loguru import logger
    # Загружаем .env из корня пакета (симлинк на shared credentials)
    pkg_root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(pkg_root / ".env")

    log_dir = Path.home() / ".local/state/logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(log_dir / "mcp-rb-gsc.log", rotation="10 MB", retention="7 days")

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())
