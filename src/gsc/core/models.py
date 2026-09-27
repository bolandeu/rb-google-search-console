from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# --- Настройки проекта (.gsc/config.toml) -------------------------------------


class CliCompat(BaseModel):
    min_version: str = "0.1.0"


class ProjectConfig(BaseModel):
    version: int = 1
    name: str
    site: str | None = None  # ресурс Search Console по умолчанию для -s/--site
    cli: CliCompat = Field(default_factory=CliCompat)


# --- Search Console -------------------------------------------------------------


class Property(BaseModel):
    """Ресурс Search Console: доменный (sc-domain:example.com) или URL-prefix (https://example.com/)."""

    site_url: str
    permission_level: str = ""  # siteOwner, siteFullUser, siteRestrictedUser, siteUnverifiedUser

    @property
    def kind(self) -> Literal["domain", "url-prefix"]:
        return "domain" if self.site_url.startswith("sc-domain:") else "url-prefix"


class Row(BaseModel):
    """Строка Search Analytics. keys: срез → значение ({"page": "https://…", "query": "…"}), в порядке dimensions.

    URL — ровно как их отдал Google, без нормализации.
    """

    keys: dict[str, str] = Field(default_factory=dict)
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0


class Issue(BaseModel):
    message: str = ""
    severity: str = ""  # WARNING, ERROR
    type: str | None = None  # только у мобильности: issueType


class RichResultItem(BaseModel):
    name: str = ""
    issues: list[Issue] = Field(default_factory=list)


class RichResult(BaseModel):
    type: str = ""  # richResultType: Breadcrumbs, FAQ, Product, …
    items: list[RichResultItem] = Field(default_factory=list)


class Inspection(BaseModel):
    """Результат URL Inspection API. Пустая строка / None — поле не пришло в ответе."""

    url: str
    property: str
    inspection_result_link: str = ""
    # индексация
    verdict: str = ""  # PASS, PARTIAL, FAIL, NEUTRAL
    coverage_state: str = ""  # «Submitted and indexed», «Crawled - currently not indexed», …
    indexing_state: str = ""
    robots_txt_state: str = ""
    page_fetch_state: str = ""
    last_crawl_time: str = ""
    crawled_as: str = ""
    # canonical
    google_canonical: str = ""
    user_canonical: str = ""
    # откуда Google знает URL
    sitemaps: list[str] = Field(default_factory=list)
    referring_urls: list[str] = Field(default_factory=list)
    # мобильность (Google её больше не отдаёт для новых проверок, но поле в API есть)
    mobile_verdict: str = ""
    mobile_issues: list[Issue] = Field(default_factory=list)
    # AMP
    amp_verdict: str = ""
    amp_issues: list[Issue] = Field(default_factory=list)
    # расширенные результаты
    rich_results_verdict: str = ""
    rich_results: list[RichResult] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)  # inspectionResult как есть


class InspectionError(BaseModel):
    """Ошибка по одному URL в inspect_many — выдаётся вместо Inspection, обход продолжается."""

    url: str
    code: str
    message: str
    status: int | None = None


class Sitemap(BaseModel):
    path: str
    last_submitted: str | None = None
    is_pending: bool = False
    is_sitemaps_index: bool = False
    type: str | None = None
    last_downloaded: str | None = None
    warnings: int = 0
    errors: int = 0


# --- PageSpeed Insights ---------------------------------------------------------


class CruxMetric(BaseModel):
    """Метрика CrUX. percentile — как в ответе (у CLS это CLS×100); value — в нормальных единицах (мс, CLS)."""

    percentile: float | None = None
    value: float | None = None
    category: str | None = None  # FAST, AVERAGE, SLOW


class Crux(BaseModel):
    """Данные реальных пользователей (Chrome UX Report) по URL или по origin."""

    id: str = ""  # URL или origin, к которому относятся данные
    overall_category: str | None = None
    lcp: CruxMetric | None = None
    inp: CruxMetric | None = None
    cls: CruxMetric | None = None
    fcp: CruxMetric | None = None
    ttfb: CruxMetric | None = None


class LabMetrics(BaseModel):
    """Лабораторные метрики Lighthouse, мс (CLS — без единиц)."""

    lcp_ms: float | None = None
    fcp_ms: float | None = None
    tbt_ms: float | None = None
    cls: float | None = None
    speed_index_ms: float | None = None
    tti_ms: float | None = None


class Audit(BaseModel):
    id: str
    title: str = ""
    score: float | None = None
    score_display_mode: str = ""  # numeric, binary, informative, notApplicable, manual, metricSavings, error
    display_value: str | None = None
    numeric_value: float | None = None
    numeric_unit: str | None = None
    details_type: str | None = None  # opportunity, table, list, …
    details: list[dict[str, Any]] = Field(default_factory=list)  # details.items как в ответе
    savings_ms: float | None = None
    savings_bytes: float | None = None
    metric_savings: dict[str, float] = Field(default_factory=dict)  # {"LCP": 1200, "FCP": 300, …}


class PageSpeedResult(BaseModel):
    url: str  # запрошенный URL
    final_url: str = ""  # URL после редиректов
    strategy: str
    fetch_time: str = ""
    lighthouse_version: str = ""  # id аудитов меняются между версиями
    scores: dict[str, float | None] = Field(default_factory=dict)  # категория → 0..1
    lab: LabMetrics = Field(default_factory=LabMetrics)
    crux_url: Crux | None = None  # по URL; None — у Google нет данных по этому URL
    crux_origin: Crux | None = None  # по origin (сайту целиком)
    crux_origin_fallback: bool = False  # данных по URL нет, Google подставил origin (crux_url тогда None)
    audits: list[Audit] = Field(default_factory=list)

    def audit(self, audit_id: str) -> Audit | None:
        return next((a for a in self.audits if a.id == audit_id), None)


class PageSpeedError(BaseModel):
    """Ошибка по одному URL в analyze_many — выдаётся вместо PageSpeedResult."""

    url: str
    code: str
    message: str
    status: int | None = None
