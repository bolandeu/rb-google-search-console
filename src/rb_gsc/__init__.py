"""rb-google-search-console — Google Search Console + PageSpeed Insights."""

from .core.client import GSCClient
from .core.pagespeed import PageSpeedClient
from .core.models import (
    SearchAnalyticsParams,
    SearchAnalyticsResult,
    SearchAnalyticsRow,
    Site,
    Sitemap,
    UrlInspectionResult,
    PageSpeedParams,
    PageSpeedResult,
)

__version__ = "0.1.0"
__all__ = [
    "GSCClient",
    "PageSpeedClient",
    "SearchAnalyticsParams",
    "SearchAnalyticsResult",
    "SearchAnalyticsRow",
    "Site",
    "Sitemap",
    "UrlInspectionResult",
    "PageSpeedParams",
    "PageSpeedResult",
]
