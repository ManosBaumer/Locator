"""Checkpoint storage for the McDonald's deliveryinfo city crawl.

Uses a cached disclosure manifest, per-city store files, and a small state file
so resume is fast and we never rewrite thousands of stores into one JSON blob.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LEGACY_CHECKPOINT_FILENAME = "deliveryinfo_progress.json"
MANIFEST_FILENAME = "deliveryinfo_manifest.json"
STATE_FILENAME = "deliveryinfo_state.json"
GEOCODES_FILENAME = "deliveryinfo_geocodes.json"
CITIES_SUBDIR = "deliveryinfo_cities"


def city_checkpoint_slug(city: str) -> str:
    return hashlib.sha1(city.encode("utf-8")).hexdigest()[:16]


class McDonaldsDeliveryinfoCheckpoint:
    def __init__(self, directory: Path, *, adapter_version: str) -> None:
        self.directory = directory
        self.adapter_version = adapter_version
        self.cities_dir = directory / CITIES_SUBDIR
        self.manifest_path = directory / MANIFEST_FILENAME
        self.state_path = directory / STATE_FILENAME
        self.geocodes_path = directory / GEOCODES_FILENAME
        self.legacy_path = directory / LEGACY_CHECKPOINT_FILENAME
        self.directory.mkdir(parents=True, exist_ok=True)
        self.cities_dir.mkdir(parents=True, exist_ok=True)

    @property
    def exists(self) -> bool:
        return (
            self.state_path.exists()
            or self.manifest_path.exists()
            or any(self.cities_dir.glob("*.json"))
            or self.legacy_path.exists()
        )

    def city_path(self, city: str) -> Path:
        return self.cities_dir / f"{city_checkpoint_slug(city)}.json"

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    def migrate_legacy_if_needed(self) -> None:
        if not self.legacy_path.exists() or self.state_path.exists():
            return
        payload = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        stores: dict[str, dict[str, Any]] = payload.get("stores") or {}
        by_city: dict[str, dict[str, dict[str, Any]]] = {}
        for store in stores.values():
            city = store.get("city")
            if not city:
                continue
            by_city.setdefault(str(city), {})[store["external_id"]] = store
        for city, city_stores in by_city.items():
            self.save_city(city, city_stores, search_requests=0, stopped_early=False)
        self.save_state(
            completed_cities=list(payload.get("completed_cities") or []),
            request_count=int(payload.get("request_count") or 0),
        )
        self.legacy_path.unlink(missing_ok=True)
        logger.info(
            "mcdonalds_deliveryinfo_legacy_checkpoint_migrated",
            extra={"city_count": len(by_city), "store_count": len(stores)},
        )

    def load_manifest(self) -> list[dict[str, str]] | None:
        if not self.manifest_path.exists():
            return None
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if payload.get("adapter_version") != self.adapter_version:
            logger.warning(
                "mcdonalds_deliveryinfo_manifest_version_mismatch",
                extra={"saved": payload.get("adapter_version"), "expected": self.adapter_version},
            )
            return None
        rows = payload.get("stores")
        return rows if isinstance(rows, list) else None

    def save_manifest(self, stores: list[dict[str, str]]) -> None:
        self._write_json(
            self.manifest_path,
            {
                "adapter_version": self.adapter_version,
                "store_count": len(stores),
                "stores": stores,
            },
        )
        logger.info(
            "mcdonalds_deliveryinfo_manifest_saved",
            extra={"path": str(self.manifest_path), "store_count": len(stores)},
        )

    def load_state(self) -> dict[str, Any]:
        self.migrate_legacy_if_needed()
        if not self.state_path.exists():
            return {"completed_cities": [], "request_count": 0}
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if payload.get("adapter_version") != self.adapter_version:
            return {"completed_cities": [], "request_count": 0}
        return {
            "completed_cities": list(payload.get("completed_cities") or []),
            "request_count": int(payload.get("request_count") or 0),
        }

    def save_state(self, *, completed_cities: list[str], request_count: int) -> None:
        self._write_json(
            self.state_path,
            {
                "adapter_version": self.adapter_version,
                "completed_cities": sorted(completed_cities),
                "request_count": request_count,
            },
        )

    def load_geocode(self, city: str) -> tuple[float, float] | None:
        if not self.geocodes_path.exists():
            return None
        payload = json.loads(self.geocodes_path.read_text(encoding="utf-8"))
        entry = (payload.get("cities") or {}).get(city)
        if not entry:
            return None
        return float(entry["lat"]), float(entry["lng"])

    def save_geocode(self, city: str, latitude: float, longitude: float) -> None:
        cities: dict[str, dict[str, float]]
        if self.geocodes_path.exists():
            payload = json.loads(self.geocodes_path.read_text(encoding="utf-8"))
            cities = dict(payload.get("cities") or {})
        else:
            cities = {}
        cities[city] = {"lat": latitude, "lng": longitude}
        self._write_json(self.geocodes_path, {"adapter_version": self.adapter_version, "cities": cities})

    def save_city(
        self,
        city: str,
        stores: dict[str, dict[str, Any]],
        *,
        search_requests: int,
        stopped_early: bool,
    ) -> None:
        self._write_json(
            self.city_path(city),
            {
                "adapter_version": self.adapter_version,
                "city": city,
                "store_count": len(stores),
                "search_requests": search_requests,
                "stopped_early": stopped_early,
                "stores": stores,
            },
        )

    def load_all_stores(self) -> dict[str, dict[str, Any]]:
        self.migrate_legacy_if_needed()
        merged: dict[str, dict[str, Any]] = {}
        for path in sorted(self.cities_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for external_id, store in (payload.get("stores") or {}).items():
                merged[external_id] = store
        if merged:
            return merged
        if self.legacy_path.exists():
            payload = json.loads(self.legacy_path.read_text(encoding="utf-8"))
            return dict(payload.get("stores") or {})
        return {}

    def clear(self) -> None:
        for path in (
            self.manifest_path,
            self.state_path,
            self.geocodes_path,
            self.legacy_path,
        ):
            path.unlink(missing_ok=True)
        if self.cities_dir.exists():
            shutil.rmtree(self.cities_dir)
        self.cities_dir.mkdir(parents=True, exist_ok=True)
        logger.info("mcdonalds_deliveryinfo_checkpoint_cleared", extra={"path": str(self.directory)})
