"""Project services: find the project folder, read and write its config file, and the check that the installed CLI is
new enough for it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w
from packaging.version import Version

from .crux import CrUX
from .errors import CliTooOld, InvalidArguments, ProjectNotInitialized
from .models import ProjectConfig
from .pagespeed import PageSpeed
from .search_console import SearchConsole
from .version import installed_version

# Derived at import time from this package's own name, so this module never
# needs template substitution: it just works under whatever package_name
# the project was generated with.
_PACKAGE_NAME = __name__.split(".")[0]
PROJECT_DIR_NAME = f".{_PACKAGE_NAME}"
CONFIG_FILE_NAME = "config.toml"


def find_project_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / PROJECT_DIR_NAME).is_dir():
            return candidate
    return None


def require_project_root(start: Path) -> Path:
    root = find_project_root(start)
    if root is None:
        raise ProjectNotInitialized(str(start))
    return root


def config_path(project_root: Path) -> Path:
    return project_root / PROJECT_DIR_NAME / CONFIG_FILE_NAME


def check_cli_compat(config: ProjectConfig) -> None:
    """Raise CliTooOld if this installed CLI is older than the project's `cli.min_version`.

    A project outlives any single CLI release; this is how it refuses to be
    driven by a CLI that predates a config field or command it relies on.
    Skipped for an uninstalled (bare source) run, which has no version, and
    for a build without a `v*` tag in reach (uv-dynamic-versioning's
    `0.0.0` fallback) — a dev checkout, not a release older than anything.
    """
    installed = installed_version()
    if installed is None or Version(installed).release == (0, 0, 0):
        return
    if Version(installed) < Version(config.cli.min_version):
        raise CliTooOld(installed, config.cli.min_version)


def load_config(project_root: Path, *, check_compat: bool = True) -> ProjectConfig:
    """Load and validate the project config, enforcing `cli.min_version` by default.

    Only `doctor` passes `check_compat=False` — it reports the mismatch as
    one of its checks instead of failing on it.
    """
    data = tomllib.loads(config_path(project_root).read_text(encoding="utf-8"))
    config = ProjectConfig.model_validate(data)
    if check_compat:
        check_cli_compat(config)
    return config


def save_config(project_root: Path, config: ProjectConfig) -> None:
    path = config_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(config.model_dump(exclude_none=True)), encoding="utf-8")


def init_project(project_root: Path, name: str, *, site: str | None = None) -> ProjectConfig:
    config = ProjectConfig(name=name, site=site)
    save_config(project_root, config)
    return config


def resolve_site(explicit: str | None, start: Path) -> str:
    """Ресурс для команды: -s/--site → `site` из .gsc/config.toml → ошибка с подсказкой."""
    if explicit:
        return explicit
    root = find_project_root(start)
    if root is not None:
        site = load_config(root).site
        if site:
            return site
    raise InvalidArguments(
        f"Не указан ресурс: передайте -s sc-domain:example.com (список — '{_PACKAGE_NAME} sites') "
        f"или задайте его проекту: '{_PACKAGE_NAME} init --site …'."
    )


def split_list(value: str | None) -> list[str]:
    """'a, b,c' → ['a', 'b', 'c']; None/'' → []."""
    return [part.strip() for part in (value or "").split(",") if part.strip()]


FILTER_OPERATORS = ("equals", "notEquals", "contains", "notContains", "includingRegex", "excludingRegex")


def parse_filter(value: str) -> dict:
    """'page:contains:/blog/' → dimensionFilter API. Выражение может содержать «:» (URL)."""
    parts = value.split(":", 2)
    if len(parts) != 3 or not all(parts):
        raise InvalidArguments(f"Фильтр '{value}': нужно СРЕЗ:ОПЕРАТОР:ВЫРАЖЕНИЕ, например page:contains:/blog/.")
    dimension, operator, expression = parts
    if operator not in FILTER_OPERATORS:
        raise InvalidArguments(f"Оператор '{operator}' не поддерживается. Доступны: {', '.join(FILTER_OPERATORS)}.")
    return {"dimension": dimension, "operator": operator, "expression": expression}


# Фабрики клиентов: команды берут клиентов только отсюда, тесты CLI подменяют их фейками из gsc.testing.


def search_console() -> SearchConsole:
    return SearchConsole()


def pagespeed() -> PageSpeed:
    return PageSpeed()


def crux() -> CrUX:
    return CrUX()
