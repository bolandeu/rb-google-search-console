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


class SitemapContent(BaseModel):
    type: str  # web, image, video, news, …
    submitted: int = 0  # сколько URL этого типа в карте
    indexed: int | None = None  # Google больше не заполняет, но поле в API есть


class Sitemap(BaseModel):
    path: str
    last_submitted: str | None = None
    is_pending: bool = False
    is_sitemaps_index: bool = False
    type: str | None = None
    last_downloaded: str | None = None
    warnings: int = 0
    errors: int = 0
    contents: list[SitemapContent] = Field(default_factory=list)


# --- PageSpeed Insights ---------------------------------------------------------


class CruxMetric(BaseModel):
    """Метрика CrUX. percentile — как в ответе (у CLS это CLS×100); value — в нормальных единицах (мс, CLS)."""

    percentile: float | None = None
    value: float | None = None
    category: str | None = None  # FAST, AVERAGE, SLOW
    # доли визитов в зонах «хорошо / нужно улучшить / плохо» (0..1, в сумме ≈ 1)
    good: float | None = None
    needs_improvement: float | None = None
    poor: float | None = None


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
    description: str = ""  # объяснение со ссылкой «подробнее» (markdown)
    explanation: str | None = None  # почему аудит не прошёл/не выполнился
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    categories: list[AuditRef] = Field(default_factory=list)  # в каких категориях аудит, с весом и группой


class AuditRef(BaseModel):
    """Место аудита в категории Lighthouse: вес в оценке (0 — не влияет) и группа (metrics, diagnostics, …)."""

    category: str
    weight: float = 0.0
    group: str | None = None


class StackPack(BaseModel):
    """Советы под платформу сайта (WordPress, React, …), которую опознал Lighthouse: id аудита → текст."""

    id: str
    title: str = ""
    descriptions: dict[str, str] = Field(default_factory=dict)


class Entity(BaseModel):
    """Владелец ресурсов на странице: сам сайт или сторонний сервис (аналитика, виджет, CDN)."""

    name: str
    is_first_party: bool = False
    is_unrecognized: bool = False
    category: str | None = None
    homepage: str | None = None
    origins: list[str] = Field(default_factory=list)


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
    category_titles: dict[str, str] = Field(default_factory=dict)  # performance → «Производительность» (по locale)
    audits: list[Audit] = Field(default_factory=list)
    stack_packs: list[StackPack] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    # Замер прошёл с проблемами (редирект, таймаут, страница не отдалась) — цифрам верить с оглядкой.
    run_warnings: list[str] = Field(default_factory=list)
    runtime_error: str | None = None  # "КОД: сообщение"; есть — результат Lighthouse недействителен
    # data:image/…;base64 — только при analyze(..., screenshots=True)
    final_screenshot: str | None = None
    full_page_screenshot: str | None = None

    def audit(self, audit_id: str) -> Audit | None:
        return next((a for a in self.audits if a.id == audit_id), None)


class PageSpeedError(BaseModel):
    """Ошибка по одному URL в analyze_many — выдаётся вместо PageSpeedResult."""

    url: str
    code: str
    message: str
    status: int | None = None


# --- Chrome UX Report API -----------------------------------------------------------


class CruxPeriod(BaseModel):
    first_date: str  # YYYY-MM-DD
    last_date: str


class CruxApiMetric(BaseModel):
    """Метрика CrUX API: p75 и доли визитов по зонам. Для долевых метрик (navigation_types,
    form_factors, largest_contentful_paint_resource_type) — только `fractions`."""

    p75: float | None = None
    good: float | None = None
    needs_improvement: float | None = None
    poor: float | None = None
    fractions: dict[str, float] = Field(default_factory=dict)


class CruxRecord(BaseModel):
    """Данные реальных пользователей за последние 28 дней (Chrome UX Report API)."""

    url: str | None = None
    origin: str | None = None
    form_factor: str | None = None  # PHONE, DESKTOP, TABLET; None — все устройства
    period: CruxPeriod | None = None
    metrics: dict[str, CruxApiMetric] = Field(default_factory=dict)  # имя метрики CrUX → значение
    normalized_url: str | None = None  # если Google нормализовал запрошенный URL


class CruxHistoryMetric(BaseModel):
    """Ряды по периодам (старые → новые); None — в этот период данных не хватило."""

    p75: list[float | None] = Field(default_factory=list)
    good: list[float | None] = Field(default_factory=list)
    needs_improvement: list[float | None] = Field(default_factory=list)
    poor: list[float | None] = Field(default_factory=list)
    fractions: dict[str, list[float | None]] = Field(default_factory=dict)


class CruxHistory(BaseModel):
    """История CrUX: по неделям, каждое значение — скользящее окно 28 дней."""

    url: str | None = None
    origin: str | None = None
    form_factor: str | None = None
    periods: list[CruxPeriod] = Field(default_factory=list)
    metrics: dict[str, CruxHistoryMetric] = Field(default_factory=dict)
