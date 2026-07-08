import asyncio
import logging
import re
from typing import Any, Callable

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.adapters.seven_eleven import _parse_amap_result_count
from app.ingestion.amap_regions import fetch_amap_province_city_tree, is_excluded_mainland_region
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

WALMART_CHINA_URL = "https://www.walmart.cn/"
AMAP_PLACE_TEXT = "https://restapi.amap.com/v3/place/text"
USER_AGENT = "LocaterBot/0.1 (+https://example.local; location aggregation research)"

DEFAULT_WALMART_KEYWORDS = ("沃尔玛(",)
DEFAULT_SAMS_KEYWORDS = ("山姆会员商店",)

WALMART_STORE_PATTERN = re.compile(r"沃尔玛\s*[\(（]")
SAMS_STORE_PATTERN = re.compile(r"山姆会员商店\s*[\(（]")


def is_walmart_hypermarket(name: str, type_field: str | None) -> bool:
    if not name or not WALMART_STORE_PATTERN.search(name):
        return False
    if "山姆" in name:
        return False
    if "有限公司" in name and "店" not in name:
        return False
    if "公交站" in name or "地铁站" in name:
        return False
    poi_type = type_field or ""
    return "沃尔玛" in poi_type or "超级市场" in poi_type


def is_sams_club_store(name: str) -> bool:
    if not name or not SAMS_STORE_PATTERN.search(name):
        return False
    if "有限公司" in name and "店" not in name:
        return False
    if "公交站" in name or "地铁站" in name:
        return False
    return True


def parse_amap_poi(poi: dict[str, Any], *, store_format: str) -> dict[str, Any] | None:
    if is_excluded_mainland_region(poi.get("pname")) or is_excluded_mainland_region(poi.get("cityname")):
        return None

    name = poi.get("name") or ""
    poi_type = poi.get("type")
    if store_format == "hypermarket":
        if not is_walmart_hypermarket(name, poi_type):
            return None
    elif store_format == "sams_club":
        if not is_sams_club_store(name):
            return None
    else:
        return None

    location = poi.get("location") or ""
    if "," not in location:
        return None

    lng_str, lat_str = location.split(",", 1)
    return {
        "source": "amap_poi",
        "store_format": store_format,
        "external_id": f"amap-{poi['id']}",
        "name": name,
        "address": poi.get("address") or None,
        "province": poi.get("pname"),
        "city": poi.get("cityname"),
        "district": poi.get("adname"),
        "phone": poi.get("tel") if poi.get("tel") not in (None, "", []) else None,
        "longitude": float(lng_str),
        "latitude": float(lat_str),
        "coordinate_system": CoordinateSystem.GCJ02.value,
        "raw": poi,
    }


@register("walmart")
class WalmartAdapter(BaseChainAdapter):
    """Walmart China hypermarkets and Sam's Club warehouses.

    Walmart China does not publish a national store-locator API. Store locations are
    collected via Amap POI text search (same approach as 7-Eleven), using strict
    name/type filters for ``沃尔玛(…)`` hypermarkets and ``山姆会员商店(…)`` clubs.
    """

    chain_slug = "walmart"
    adapter_version = "0.1.1"
    source_url = WALMART_CHINA_URL

    def __init__(self) -> None:
        self.settings = get_settings()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        if not self.settings.amap_api_key:
            logger.warning("walmart_amap_skipped", extra={"reason": "amap_api_key_missing"})
            return []

        headers = {"User-Agent": USER_AGENT}
        stores: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=60, headers=headers, follow_redirects=True) as client:
            walmart_regions = await self._walmart_city_regions(client)
            sams_regions = await self._sams_search_regions(client)

            for region in walmart_regions:
                for keyword in self._walmart_keywords():
                    region_stores = await self._fetch_region(
                        client,
                        region,
                        keyword,
                        "hypermarket",
                        lambda poi, kw=keyword: is_walmart_hypermarket(poi.get("name") or "", poi.get("type")),
                    )
                    for store in region_stores:
                        external_id = store["external_id"]
                        if external_id in seen_ids:
                            continue
                        seen_ids.add(external_id)
                        stores.append(store)
                    await asyncio.sleep(0.02)

            for region in sams_regions:
                for keyword in self._sams_keywords():
                    region_stores = await self._fetch_region(
                        client,
                        region,
                        keyword,
                        "sams_club",
                        lambda poi, kw=keyword: is_sams_club_store(poi.get("name") or ""),
                    )
                    for store in region_stores:
                        external_id = store["external_id"]
                        if external_id in seen_ids:
                            continue
                        seen_ids.add(external_id)
                        stores.append(store)
                    await asyncio.sleep(0.02)

        logger.info(
            "walmart_fetch_complete",
            extra={
                "total": len(stores),
                "hypermarket": sum(1 for store in stores if store.get("store_format") == "hypermarket"),
                "sams_club": sum(1 for store in stores if store.get("store_format") == "sams_club"),
            },
        )
        return stores

    async def _fetch_region(
        self,
        client: httpx.AsyncClient,
        region: str,
        keyword: str,
        store_format: str,
        matcher: Callable[[dict[str, Any]], bool],
    ) -> list[dict[str, Any]]:
        stores: list[dict[str, Any]] = []
        page = 1
        while page <= 40:
            response = await client.get(
                AMAP_PLACE_TEXT,
                params={
                    "key": self.settings.amap_api_key,
                    "keywords": keyword,
                    "city": region,
                    "offset": 25,
                    "page": page,
                    "extensions": "base",
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "1":
                logger.warning(
                    "walmart_amap_error",
                    extra={"region": region, "keyword": keyword, "page": page, "info": payload.get("info")},
                )
                break

            pois = payload.get("pois") or []
            if not pois:
                break

            for poi in pois:
                if not isinstance(poi, dict) or not poi.get("id"):
                    continue
                if not matcher(poi):
                    continue
                parsed = parse_amap_poi(poi, store_format=store_format)
                if parsed is None:
                    continue
                stores.append(parsed)

            if len(pois) < 25:
                break

            page += 1
            await asyncio.sleep(0.02)

        return stores

    async def _walmart_city_regions(self, client: httpx.AsyncClient) -> list[str]:
        if self.settings.walmart_amap_cities:
            return [city.strip() for city in self.settings.walmart_amap_cities.split(",") if city.strip()]

        tree = await fetch_amap_province_city_tree(client, self.settings.amap_api_key)
        keyword = self._walmart_keywords()[0]
        regions: list[str] = []

        for province in tree:
            if province.cities:
                for city in province.cities:
                    if await self._probe_amap_count(client, city, keyword) > 0:
                        regions.append(city)
                    await asyncio.sleep(0.02)
                continue

            if await self._probe_amap_count(client, province.short_name, keyword) > 0:
                regions.append(province.short_name)

        logger.info("walmart_hypermarket_regions_planned", extra={"search_regions": len(regions)})
        return regions

    async def _sams_search_regions(self, client: httpx.AsyncClient) -> list[str]:
        tree = await fetch_amap_province_city_tree(client, self.settings.amap_api_key)
        regions: list[str] = []
        skipped_provinces = 0
        keyword = self._sams_keywords()[0]

        for province in tree:
            count = await self._probe_amap_count(client, province.short_name, keyword)
            if count == 0:
                skipped_provinces += 1
                continue
            if count >= 1000 and province.cities:
                regions.extend(province.cities)
            else:
                regions.append(province.short_name)

        logger.info(
            "walmart_sams_regions_planned",
            extra={"search_regions": len(regions), "skipped_provinces": skipped_provinces},
        )
        return regions

    async def _probe_amap_count(self, client: httpx.AsyncClient, region: str, keyword: str) -> int:
        response = await client.get(
            AMAP_PLACE_TEXT,
            params={
                "key": self.settings.amap_api_key,
                "keywords": keyword,
                "city": region,
                "offset": 1,
                "page": 1,
                "extensions": "base",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "1":
            return 0
        return _parse_amap_result_count(payload.get("count"))

    def _walmart_keywords(self) -> tuple[str, ...]:
        raw = self.settings.walmart_amap_keywords
        if raw:
            parts = tuple(keyword.strip() for keyword in raw.split(",") if keyword.strip())
            if parts:
                return tuple(dict.fromkeys(parts))
        return DEFAULT_WALMART_KEYWORDS

    def _sams_keywords(self) -> tuple[str, ...]:
        raw = self.settings.walmart_sams_amap_keywords
        if raw:
            parts = tuple(keyword.strip() for keyword in raw.split(",") if keyword.strip())
            if parts:
                return tuple(dict.fromkeys(parts))
        return DEFAULT_SAMS_KEYWORDS

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            logger.warning("walmart_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
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
            source_type=payload.get("source", "amap_poi"),
            source_url=AMAP_PLACE_TEXT,
            raw_payload=payload.get("raw", payload),
        )
