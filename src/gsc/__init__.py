"""gsc — Google Search Console и PageSpeed Insights: библиотека и CLI.

Публичный API библиотеки — всё, что перечислено в __all__ (меняется только по
SemVer). Импорт не трогает сеть, keychain и CLI: ключ читается при первом запросе.

    import gsc

    sc = gsc.SearchConsole()
    site = sc.property_for("https://example.com/")
    for row in sc.iter_search_analytics(site, dimensions=["page", "query"]):
        ...
    for item in sc.inspect_many(urls, site, limit=500):
        ...
    ps = gsc.PageSpeed()
    result = ps.analyze("https://example.com/", "mobile")        # все 4 категории
    history = gsc.CrUX().history(origin="https://example.com", form_factor="PHONE")

Для тестов без сети — gsc.testing.FakeSearchConsole / FakePageSpeed / FakeCrUX.
"""

from __future__ import annotations

from .core.auth import AuthStatus, auth_status
from .core.crux import CrUX, parse_crux_history, parse_crux_record
from .core.errors import ApiError, CliError, NotAuthorized, PropertyNotFound, QuotaExceeded
from .core.models import (
    Audit,
    AuditRef,
    Crux,
    CruxApiMetric,
    CruxHistory,
    CruxHistoryMetric,
    CruxMetric,
    CruxPeriod,
    CruxRecord,
    Entity,
    Inspection,
    InspectionError,
    Issue,
    LabMetrics,
    PageSpeedError,
    PageSpeedResult,
    Property,
    RichResult,
    RichResultItem,
    Row,
    Sitemap,
    SitemapContent,
    StackPack,
)
from .core.pagespeed import PageSpeed, parse_pagespeed
from .core.search_console import SearchAnalyticsRows, SearchConsole, default_range, parse_inspection, property_for
from .core.version import DEV_VERSION, installed_version

__version__ = installed_version() or DEV_VERSION

__all__ = [
    "ApiError",
    "Audit",
    "AuditRef",
    "AuthStatus",
    "CliError",
    "CrUX",
    "Crux",
    "CruxApiMetric",
    "CruxHistory",
    "CruxHistoryMetric",
    "CruxMetric",
    "CruxPeriod",
    "CruxRecord",
    "Entity",
    "Inspection",
    "InspectionError",
    "Issue",
    "LabMetrics",
    "NotAuthorized",
    "PageSpeed",
    "PageSpeedError",
    "PageSpeedResult",
    "Property",
    "PropertyNotFound",
    "QuotaExceeded",
    "RichResult",
    "RichResultItem",
    "Row",
    "SearchAnalyticsRows",
    "SearchConsole",
    "Sitemap",
    "SitemapContent",
    "StackPack",
    "__version__",
    "auth_status",
    "default_range",
    "parse_crux_history",
    "parse_crux_record",
    "parse_inspection",
    "parse_pagespeed",
    "property_for",
]
