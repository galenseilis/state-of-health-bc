"""Loading and validation of the data-source catalogue."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_PATH = ROOT / "data" / "catalogue" / "sources.yml"

REQUIRED_FIELDS = (
    "key",
    "title",
    "publisher",
    "url",
    "form",
    "domains",
    "resolution",
    "geography",
    "coverage",
    "frequency",
    "refresh",
    "licence",
    "access",
    "origin",
    "temporal_behaviour",
    "download",
)

FORMS = {
    "microdata",
    "indicator_table",
    "dashboard",
    "report_figure",
    "api",
    "catalogue",
}
ORIGINS = {"bc", "canada", "international"}
TEMPORAL = {"trending", "seasonal", "shock_prone", "stable"}
ACCESS = {"public", "registration", "request"}
DOWNLOAD_KINDS = {"manual", "direct", "api_json"}


class CatalogueError(ValueError):
    """Raised when the catalogue is malformed."""


@dataclass
class Source:
    """A single data source in the catalogue.

    Attributes:
        key: Stable identifier for the source.
        title: Human-readable title of the source.
        publisher: Publishing organisation.
        url: Landing page URL.
        form: Form of the source (microdata, indicator_table, dashboard, etc).
        domains: Domains the source covers.
        resolution: Geographic/administrative resolutions available.
        geography: Geographic coverage description.
        coverage: Temporal coverage description.
        frequency: Update frequency.
        refresh: Refresh cadence.
        licence: Licensing terms.
        access: Access model (public, registration, request).
        origin: Origin geography (bc, canada, international).
        temporal_behaviour: Temporal behaviour classification.
        download: Download configuration dictionary.
        indicators: Indicators this source provides.
        quality_notes: Quality-related notes.
        citation: Citation string if provided.
        form_of_access: Description of how access is obtained.
        reaches_bc_via: Mechanism by which external sources reach BC.
    """

    key: str
    title: str
    publisher: str
    url: str
    form: str
    domains: list[str]
    resolution: list[str]
    geography: str
    coverage: str
    frequency: str
    refresh: str
    licence: str
    access: str
    origin: str
    temporal_behaviour: str
    download: dict[str, Any]
    indicators: list[str] = field(default_factory=list)
    quality_notes: str = ""
    citation: str | None = None
    form_of_access: str = ""
    reaches_bc_via: str | None = None

    @property
    def automated(self) -> bool:
        """Return True if this source can be fetched automatically."""
        return self.download.get("kind") in {"direct", "api_json"}


def _require(source: dict[str, Any], field_name: str, index: int) -> Any:
    """Require a field exists in a source dict.

    Args:
        source: Source dictionary from YAML.
        field_name: Name of required field.
        index: Index of source in the catalogue.

    Returns:
        The field value.

    Raises:
        CatalogueError: If the field is missing.
    """
    if field_name not in source:
        raise CatalogueError(f"source #{index}: missing required field '{field_name}'")
    return source[field_name]


def _validate_enum(value: str, allowed: set[str], field_name: str, key: str) -> None:
    """Validate that a string value is in the allowed set.

    Args:
        value: Value to validate.
        allowed: Set of allowed values.
        field_name: Name of field being validated.
        key: Source key.

    Raises:
        CatalogueError: If value is not in allowed set.
    """
    if value not in allowed:
        raise CatalogueError(
            f"source '{key}': field '{field_name}' has value '{value}'; "
            f"expected one of {sorted(allowed)}"
        )


def load(path: Path | None = None) -> list[Source]:
    """Load the data source catalogue from a YAML file.

    Args:
        path: Optional path to the catalogue YAML. Defaults to the project
            catalogue at data/catalogue/sources.yml.

    Returns:
        list[Source]: List of catalogue sources.

    Raises:
        CatalogueError: If the catalogue is missing, malformed, or contains
            invalid values.
    """
    path = path or CATALOGUE_PATH
    if not path.exists():
        raise CatalogueError(f"catalogue not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "sources" not in data:
        raise CatalogueError("catalogue must be a mapping with a 'sources' list")

    sources: list[Source] = []
    seen: set[str] = set()
    for index, raw in enumerate(data["sources"]):
        if not isinstance(raw, dict):
            raise CatalogueError(f"source #{index}: expected a mapping")
        for field_name in REQUIRED_FIELDS:
            _require(raw, field_name, index)
        key = raw["key"]
        if key in seen:
            raise CatalogueError(f"duplicate source key: {key}")
        seen.add(key)
        _validate_enum(raw["form"], FORMS, "form", key)
        _validate_enum(raw["origin"], ORIGINS, "origin", key)
        _validate_enum(raw["temporal_behaviour"], TEMPORAL, "temporal_behaviour", key)
        _validate_enum(raw["access"], ACCESS, "access", key)
        download = raw["download"]
        if not isinstance(download, dict) or "kind" not in download:
            raise CatalogueError(f"source '{key}': 'download' must include a 'kind'")
        _validate_enum(download["kind"], DOWNLOAD_KINDS, "download.kind", key)
        if download["kind"] in {"direct", "api_json"} and "url" not in download:
            raise CatalogueError(
                f"source '{key}': automated downloads require 'download.url'"
            )
        domains = raw["domains"]
        if not isinstance(domains, list):
            raise CatalogueError(f"source '{key}': 'domains' must be a list")
        sources.append(
            Source(
                key=key,
                title=raw["title"],
                publisher=raw["publisher"],
                url=raw["url"],
                form=raw["form"],
                domains=domains,
                resolution=list(raw["resolution"]),
                geography=raw["geography"],
                coverage=raw["coverage"],
                frequency=raw["frequency"],
                refresh=raw["refresh"],
                licence=raw["licence"],
                access=raw["access"],
                origin=raw["origin"],
                temporal_behaviour=raw["temporal_behaviour"],
                download=download,
                indicators=list(raw.get("indicators", [])),
                quality_notes=raw.get("quality_notes", ""),
                citation=raw.get("citation"),
                form_of_access=raw.get("form_of_access", ""),
                reaches_bc_via=raw.get("reaches_bc_via"),
            )
        )
    return sources
