"""KFC mainland China store ingestion via the official order store-portal API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.adapters.kfc_store_api import (
    DEFAULT_BASE_URL,
    DEFAULT_GRID_SPAN_KM,
    DEFAULT_GRID_STEP_KM,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SEARCH_KEYWORD,
    DEFAULT_USER_AGENT,
    EXCLUDED_GB_CITY_PREFIXES,
    KfcStorePortalClient,
)
from app.ingestion.dedup_keys import make_content_external_id
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

SOURCE_URL = DEFAULT_BASE_URL


def parse_kfc_store_portal_row(row: dict[str, Any]) -> dict[str, Any] | None:
    store_code = row.get("storecode") or row.get("storeCode")
    name = (row.get("storename") or row.get("storeName") or "").strip()
    address = (row.get("address") or "").strip()
    if not store_code or not name or not address:
        return None

    city = row.get("cityName") or row.get("city")
    district = row.get("districtName") or row.get("district")
    gb_city_code = row.get("gbCityCode")
    if gb_city_code and str(gb_city_code).startswith(EXCLUDED_GB_CITY_PREFIXES):
        return None

    latitude = _pick_float(row, "lat", "latitude")
    longitude = _pick_float(row, "lng", "lon", "longitude")
    if latitude is None or longitude is None:
        return None

    display_name = name
    if "肯德基" not in display_name and "KFC" not in display_name.upper():
        display_name = f"肯德基{display_name}"

    record: dict[str, Any] = {
        "source": "kfc_store_portal",
        "external_id": f"kfc-{store_code}",
        "name": display_name,
        "address": address,
        "city": city,
        "district": district,
        "phone": row.get("phone") or None,
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_system": CoordinateSystem.GCJ02.value,
        "store_code": store_code,
        "raw": row,
    }
    return record


def parse_kfc_store_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Legacy GetStoreList.ashx row parser kept for tests/backward compatibility."""
    name = (row.get("storeName") or row.get("name") or "").strip()
    address = (row.get("addressDetail") or row.get("address") or "").strip()
    if not name or not address:
        return None

    store_code = row.get("storeCode") or row.get("storeId") or row.get("code")
    latitude = _pick_float(row, "lat", "latitude", "mapLat", "y")
    longitude = _pick_float(row, "lng", "lon", "longitude", "mapLng", "x")

    record: dict[str, Any] = {
        "source": "kfc_official",
        "name": name if "肯德基" in name or "KFC" in name.upper() else f"肯德基{name}",
        "address": address,
        "province": row.get("provinceName") or row.get("province"),
        "city": row.get("cityName") or row.get("city"),
        "district": row.get("districtName") or row.get("district"),
        "phone": row.get("pro") or row.get("phone"),
        "store_code": store_code,
        "raw": row,
    }
    if latitude is not None and longitude is not None:
        record["latitude"] = latitude
        record["longitude"] = longitude
        record["coordinate_system"] = CoordinateSystem.GCJ02.value

    if store_code:
        record["external_id"] = f"kfc-{store_code}"
    else:
        record["external_id"] = make_content_external_id("kfc", record)
    return record


def parse_kfc_store_list_payload(payload: Any) -> tuple[int, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected KFC payload type: {type(payload).__name__}")

    table = payload.get("Table") or []
    rowcount = 0
    if table and isinstance(table[0], dict):
        rowcount = int(table[0].get("rowcount") or 0)

    rows = payload.get("Table1") or []
    stores: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = parse_kfc_store_row(row)
        if parsed is not None:
            stores.append(parsed)
    return rowcount, stores


def _pick_float(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


@register("kfc")
class KfcAdapter(BaseChainAdapter):
    chain_slug = "kfc"
    adapter_version = "0.2.1"
    source_url = SOURCE_URL

    def __init__(self) -> None:
        self.settings = get_settings()
        base_url = str(self.settings.kfc_store_portal_url or DEFAULT_BASE_URL)
        self.client = KfcStorePortalClient(
            base_url=base_url,
            user_agent=DEFAULT_USER_AGENT,
            search_keyword=self.settings.kfc_search_keyword or DEFAULT_SEARCH_KEYWORD,
            page_size=self.settings.kfc_page_size or DEFAULT_PAGE_SIZE,
            grid_span_km=self.settings.kfc_grid_span_km or DEFAULT_GRID_SPAN_KM,
            grid_step_km=self.settings.kfc_grid_step_km or DEFAULT_GRID_STEP_KM,
        )
        self.city_concurrency = max(1, int(self.settings.kfc_city_concurrency or 5))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        stores: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            cities = await self.client.fetch_cities(client)
            logger.info("kfc_cities_loaded", extra={"count": len(cities)})

            semaphore = asyncio.Semaphore(self.city_concurrency)

            async def crawl_city(city: dict[str, Any]) -> list[dict[str, Any]]:
                async with semaphore:
                    try:
                        rows = await self.client.fetch_city_stores_by_grid(client, city)
                    except httpx.HTTPError as exc:
                        logger.warning(
                            "kfc_city_crawl_failed",
                            extra={
                                "city": city.get("cityNameZh"),
                                "gbCityCode": city.get("gbCityCode"),
                                "error": str(exc),
                            },
                        )
                        return []
                    await asyncio.sleep(0.02)
                    return rows

            results = await asyncio.gather(*(crawl_city(city) for city in cities))
            for city_rows in results:
                for row in city_rows:
                    parsed = parse_kfc_store_portal_row(row)
                    if parsed is None or parsed["external_id"] in seen_ids:
                        continue
                    seen_ids.add(parsed["external_id"])
                    stores.append(parsed)

        logger.info(
            "kfc_fetch_complete",
            extra={"total": len(stores), "cities": len(cities)},
        )
        return stores

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            logger.warning("kfc_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
            return []

        parsed: list[RawLocation] = []
        for store in raw_data:
            if not isinstance(store, dict) or not store.get("external_id"):
                continue
            parsed.append(RawLocation(payload=store))
        return parsed

    async def normalize(self, location: RawLocation) -> NormalizedLocation:
        payload = location.payload
        coordinate_system = CoordinateSystem(
            payload.get("coordinate_system", CoordinateSystem.GCJ02.value)
        )
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")

        return NormalizedLocation(
            external_id=str(payload["external_id"]),
            name=payload.get("name"),
            address=payload.get("address"),
            province=None,
            city=payload.get("city"),
            district=payload.get("district"),
            postal_code=None,
            latitude=float(latitude) if latitude is not None else None,
            longitude=float(longitude) if longitude is not None else None,
            coordinate_system=coordinate_system,
            source_type=payload.get("source", "kfc_store_portal"),
            source_url=self.source_url,
            raw_payload=payload.get("raw", payload),
        )
