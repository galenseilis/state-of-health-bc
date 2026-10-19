"""Fetching and verification for catalogued data sources."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .catalogue import ROOT, Source, load

RAW_DIR = ROOT / "data" / "raw"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
USER_AGENT = "sohbc/0.1 (+https://galenseilis.github.io/state-of-health-bc)"
TIMEOUT = 30


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest() -> dict[str, Any]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"schema_version": 1, "sources": {}}


def write_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def check_url(url: str) -> dict[str, Any]:
    """Return reachability information for a URL (follows redirects)."""
    try:
        response = requests.get(
            url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, stream=True
        )
        reachable = response.status_code < 400
        return {
            "url": url,
            "status": response.status_code,
            "final_url": response.url,
            "reachable": reachable,
        }
    except requests.RequestException as exc:
        return {"url": url, "status": None, "final_url": None, "reachable": False, "error": str(exc)}


def check_source(source: Source, include_download: bool = False) -> list[dict[str, Any]]:
    results = [check_url(source.url)]
    if include_download and source.automated:
        results.append(check_url(source.download["url"]))
    for result in results:
        result["key"] = source.key
    return results


def fetch_source(source: Source) -> dict[str, Any]:
    """Fetch one automated source into data/raw/<key>/."""
    if not source.automated:
        return {"key": source.key, "status": "manual", "detail": source.form_of_access}

    kind = source.download["kind"]
    url = source.download["url"]
    default_name = Path(url.split("?")[0]).name or f"{source.key}.dat"
    filename = source.download.get("filename", default_name)
    target_dir = RAW_DIR / source.key
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename

    response = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()

    if kind == "api_json":
        payload = response.json()
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        target.write_bytes(response.content)

    return {
        "key": source.key,
        "status": "fetched",
        "url": url,
        "final_url": response.url,
        "http_status": response.status_code,
        "path": str(target.relative_to(ROOT)),
        "bytes": target.stat().st_size,
        "sha256": _sha256(target),
        "fetched_at": _now(),
    }


def run_fetch(keys: list[str] | None = None, everything: bool = False) -> list[dict[str, Any]]:
    sources = load()
    selected = [s for s in sources if everything or (keys and s.key in keys)]
    if keys:
        unknown = set(keys) - {s.key for s in sources}
        if unknown:
            raise SystemExit(f"unknown source key(s): {', '.join(sorted(unknown))}")

    manifest = read_manifest()
    results: list[dict[str, Any]] = []
    for source in selected:
        record = fetch_source(source)
        results.append(record)
        if record.get("status") == "fetched":
            manifest["sources"][source.key] = record
        elif record.get("status") == "manual":
            manifest["sources"].setdefault(source.key, {})["status"] = "manual"
    manifest["updated_at"] = _now()
    write_manifest(manifest)
    return results
