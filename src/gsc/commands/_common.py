"""Общие параметры команд Search Console."""

from __future__ import annotations

from pathlib import Path

import typer

from ..core import services

SiteOption = typer.Option(
    None,
    "--site",
    "-s",
    help="Ресурс Search Console: sc-domain:example.com или https://example.com/. "
    "По умолчанию — site из .gsc/config.toml проекта.",
)


def resolve_site(ctx: typer.Context, site: str | None) -> str:
    return services.resolve_site(site, Path(ctx.obj.get("project") or Path.cwd()))
