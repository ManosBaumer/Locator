import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.amap_regions import is_excluded_mainland_coordinates, is_excluded_mainland_text
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

SEVEN_FRESH_HOME = "https://www.7fresh.com/"
DEFAULT_API_BASE = "https://www.7fresh.com/sevenFresh/api"
USER_AGENT = "Mozilla/5.0 (compatible; LocaterBot/0.1; store aggregation research)"

SUPERMARKET_TYPE_ID = "13"
LIFE_TYPE_ID = "14"

STORE_FORMATS: tuple[tuple[str, str, str], ...] = (
    ("supermarket", SUPERMARKET_TYPE_ID, "七鲜超市"),
    ("life", LIFE_TYPE_ID, "七鲜生活"),
)


def parse_store_record(record: dict[str, Any], *, store_format: str, format_label: str) -> dict[str, Any] | None:
    store_id = record.get("id")
    name = (record.get("name") or "").strip()
    address = (record.get("address") or "").strip() or None
    if not store_id or not name:
        return None

    # The official API mislabels coordinates: "longitude" holds latitude and vice versa.
    lat_raw = record.get("longitude")
    lng_raw = record.get("latitude")
    if lat_raw is None or lng_raw is None:
        return None

    latitude = float(lat_raw)
    longitude = float(lng_raw)
    if is_excluded_mainland_coordinates(longitude, latitude):
        return None
    if address and is_excluded_mainland_text(address):
        return None

    prefix = "sm" if store_format == "supermarket" else "life"
    return {
        "external_id": f"7fresh-{prefix}-{store_id}",
        "store_format": store_format,
        "format_label": format_label,
        "name": f"{format_label} {name}",
        "address": address,
        "province": None,
        "city": None,
        "district": None,
        "phone": None,
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_system": CoordinateSystem.GCJ02.value,
        "raw": record,
    }


@register("7fresh")
class SevenFreshAdapter(BaseChainAdapter):
    """7FRESH / 七鲜 mainland China stores.

    Store lists come from the official 7fresh website API:
    ``POST /sevenFresh/api/city/list`` and ``POST /sevenFresh/api/store/list``.
    ``typeId`` 13 = 七鲜超市 (supermarket), 14 = 七鲜生活 (smaller neighborhood format).
    """

    chain_slug = "7fresh"
    adapter_version = "0.1.0"
    source_url = SEVEN_FRESH_HOME

    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.seven_fresh_api_base:
            self.api_base = str(self.settings.seven_fresh_api_base).rstrip("/")
        else:
            self.api_base = DEFAULT_API_BASE

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": SEVEN_FRESH_HOME,
            "Origin": "https://www.7fresh.com",
            "Content-Type": "application/json",
        }
        stores: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
            for store_format, type_id, format_label in STORE_FORMATS:
                format_count = 0
                cities = await self._fetch_cities(client, type_id)
                for city in cities:
                    city_id = city.get("id")
                    city_name = city.get("name")
                    if not city_id:
                        continue
                    rows = await self._fetch_stores(client, city_id=city_id, type_id=type_id)
                    for row in rows:
                        parsed = parse_store_record(
                            row,
                            store_format=store_format,
                            format_label=format_label,
                        )
                        if parsed is None:
                            continue
                        if city_name and not parsed.get("city"):
                            parsed["city"] = city_name
                        if parsed["external_id"] in seen_ids:
                            continue
                        seen_ids.add(parsed["external_id"])
                        stores.append(parsed)
                        format_count += 1

                logger.info(
                    "seven_fresh_format_fetched",
                    extra={"store_format": store_format, "count": format_count},
                )

        logger.info(
            "seven_fresh_fetch_complete",
            extra={
                "total": len(stores),
                "supermarket": sum(1 for s in stores if s.get("store_format") == "supermarket"),
                "life": sum(1 for s in stores if s.get("store_format") == "life"),
            },
        )
        return stores

    async def _post(self, client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = await client.post(f"{self.api_base}{path}", json=body)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected 7fresh response type: {type(payload).__name__}")
        if payload.get("code") not in (0, "0"):
            raise ValueError(f"7fresh API error: {payload.get('message')}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("7fresh API response missing data object")
        return data

    async def _fetch_cities(self, client: httpx.AsyncClient, type_id: str) -> list[dict[str, Any]]:
        data = await self._post(
            client,
            "/city/list",
            {
                "page": {"pageNumber": 1, "pageSize": -1},
                "requestData": {"typeId": type_id, "isRecruit": False},
            },
        )
        cities = data.get("list") or []
        return [city for city in cities if isinstance(city, dict)]

    async def _fetch_stores(
        self, client: httpx.AsyncClient, *, city_id: str, type_id: str
    ) -> list[dict[str, Any]]:
        data = await self._post(
            client,
            "/store/list",
            {
                "page": {"pageNumber": 1, "pageSize": -1},
                "requestData": {"cityId": city_id, "typeId": type_id},
            },
        )
        stores = data.get("list") or []
        return [store for store in stores if isinstance(store, dict)]

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            logger.warning("seven_fresh_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
            return []

        parsed: list[RawLocation] = []
        for store in raw_data:
            if not isinstance(store, dict) or not store.get("external_id"):
                continue
            if store.get("latitude") is None or store.get("longitude") is None:
                continue
            parsed.append(RawLocation(payload=store))
        return parsed

    async def normalize(self, location: RawLocation) -> NormalizedLocation:
        payload = location.payload
        coordinate_system = CoordinateSystem(payload.get("coordinate_system", CoordinateSystem.GCJ02.value))

        return NormalizedLocation(
            external_id=str(payload["external_id"]),
            name=payload.get("name"),
            address=payload.get("address"),
            province=payload.get("province"),
            city=payload.get("city"),
            district=payload.get("district"),
            postal_code=None,
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            coordinate_system=coordinate_system,
            source_type=f"7fresh_{payload.get('store_format', 'unknown')}",
            source_url=f"{self.api_base}/store/list",
            raw_payload={
                **(payload.get("raw") or {}),
                "store_format": payload.get("store_format"),
                "format_label": payload.get("format_label"),
            },
        )
