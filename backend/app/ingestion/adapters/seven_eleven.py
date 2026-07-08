import asyncio
import logging
import re
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.amap_regions import fetch_amap_province_city_tree, is_excluded_mainland_region
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

CHENGDU_API = "http://www.7-11cd.cn/AJAX/shop.ashx"
CHENGDU_LOCATOR = "http://www.7-11cd.cn/shop/nearShop.aspx"
AMAP_PLACE_TEXT = "https://restapi.amap.com/v3/place/text"
USER_AGENT = "LocaterBot/0.1 (+https://example.local; location aggregation research)"
DEFAULT_AMAP_KEYWORDS = ("7-ELEVEN", "7-11便利店", "7-ELEVEn")

# Typical Amap listing: 7-ELEVEn(店名)
STORE_NAME_PATTERN = re.compile(r"7[\s\-]?ELEVEN?\s*[\(（]", re.IGNORECASE)


def is_store_name(name: str) -> bool:
    if not name:
        return False
    if "有限公司" in name and "店" not in name:
        return False
    if "公交站" in name or "地铁站" in name:
        return False
    return bool(STORE_NAME_PATTERN.search(name))


def parse_chengdu_store(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "chengdu_official",
        "external_id": f"cd-{record['id']}",
        "name": record.get("shopName"),
        "address": record.get("address"),
        "city_full_name": record.get("cityFullName"),
        "phone": record.get("phone"),
        "open_date": record.get("openDate"),
        "longitude": float(record["bMap_lng"]),
        "latitude": float(record["bMap_lat"]),
        "coordinate_system": CoordinateSystem.BD09.value,
        "raw": record,
    }


def parse_amap_poi(poi: dict[str, Any]) -> dict[str, Any] | None:
    if is_excluded_mainland_region(poi.get("pname")) or is_excluded_mainland_region(poi.get("cityname")):
        return None

    name = poi.get("name") or ""
    if not is_store_name(name):
        return None

    location = poi.get("location") or ""
    if "," not in location:
        return None

    lng_str, lat_str = location.split(",", 1)
    return {
        "source": "amap_poi",
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


def _parse_amap_result_count(count: str | int | None) -> int:
    if count is None:
        return 0
    if isinstance(count, int):
        return count
    text = str(count).strip()
    if text.endswith("+"):
        return int(text[:-1] or "0")
    return int(text or "0")


def split_city_full_name(city_full_name: str | None) -> tuple[str | None, str | None, str | None]:
    if not city_full_name:
        return None, None, None

    match = re.match(r"(.+?省)(.+?市)(.*)", city_full_name)
    if match:
        return match.group(1), match.group(2), match.group(3) or None

    match = re.match(r"(北京市|上海市|天津市|重庆市)(.*)", city_full_name)
    if match:
        return match.group(1), match.group(1), match.group(2) or None

    return None, city_full_name, None


@register("7-eleven")
class SevenElevenAdapter(BaseChainAdapter):
    """7-Eleven mainland China.

    Chengdu stores come from the regional licensee JSON API (BD-09 coords).
    There is no national official feed; other regions are collected via Amap POI
    text search across all provinces and prefecture-level cities.
    """

    chain_slug = "7-eleven"
    adapter_version = "0.2.2"
    source_url = CHENGDU_LOCATOR

    def __init__(self) -> None:
        self.settings = get_settings()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT}
        stores: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=60, headers=headers, follow_redirects=True) as client:
            chengdu = await self._fetch_chengdu(client)
            for store in chengdu:
                if store["external_id"] not in seen_ids:
                    seen_ids.add(store["external_id"])
                    stores.append(store)

            amap_stores = await self._fetch_amap(client)
            for store in amap_stores:
                if store["external_id"] in seen_ids:
                    continue
                seen_ids.add(store["external_id"])
                stores.append(store)

        logger.info(
            "seven_eleven_fetch_complete",
            extra={
                "total": len(stores),
                "chengdu": sum(1 for s in stores if s["source"] == "chengdu_official"),
                "amap": sum(1 for s in stores if s["source"] == "amap_poi"),
            },
        )
        return stores

    async def _fetch_chengdu(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        city_id = self.settings.seven_eleven_chengdu_city_id
        response = await client.get(
            CHENGDU_API,
            params={"action": "getList", "cityID": city_id},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            logger.warning("seven_eleven_chengdu_unexpected_shape", extra={"type": type(payload).__name__})
            return []

        parsed = [parse_chengdu_store(record) for record in payload if isinstance(record, dict)]
        logger.info("seven_eleven_chengdu_fetched", extra={"count": len(parsed)})
        return parsed

    async def _fetch_amap(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        if not self.settings.amap_api_key:
            logger.warning("seven_eleven_amap_skipped", extra={"reason": "amap_api_key_missing"})
            return []

        keywords = self._amap_keywords()
        regions = await self._amap_search_regions(client, keywords[0])
        stores: list[dict[str, Any]] = []
        seen_amap_ids: set[str] = set()

        for region in regions:
            for keyword in keywords:
                page = 1
                while page <= 40:
                    response = await client.get(
                        AMAP_PLACE_TEXT,
                        params={
                            "key": self.settings.amap_api_key,
                            "keywords": keyword,
                            "city": region,
                            "types": "060200",
                            "offset": 25,
                            "page": page,
                            "extensions": "base",
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("status") != "1":
                        logger.warning(
                            "seven_eleven_amap_error",
                            extra={"region": region, "keyword": keyword, "page": page, "info": payload.get("info")},
                        )
                        break

                    pois = payload.get("pois") or []
                    if not pois:
                        break

                    for poi in pois:
                        if not isinstance(poi, dict) or not poi.get("id"):
                            continue
                        if poi["id"] in seen_amap_ids:
                            continue
                        parsed = parse_amap_poi(poi)
                        if parsed is None:
                            continue
                        if parsed.get("city") == "成都市":
                            continue
                        seen_amap_ids.add(poi["id"])
                        stores.append(parsed)

                    if len(pois) < 25:
                        break

                    page += 1
                    await asyncio.sleep(0.02)

                await asyncio.sleep(0.02)

        logger.info(
            "seven_eleven_amap_fetched",
            extra={"count": len(stores), "regions": len(regions), "keywords": len(keywords)},
        )
        return stores

    async def _amap_search_regions(self, client: httpx.AsyncClient, probe_keyword: str) -> list[str]:
        if self.settings.seven_eleven_amap_cities:
            return [city.strip() for city in self.settings.seven_eleven_amap_cities.split(",") if city.strip()]

        tree = await fetch_amap_province_city_tree(client, self.settings.amap_api_key)
        regions: list[str] = []
        skipped_provinces = 0

        for province in tree:
            count = await self._probe_amap_count(client, province.short_name, probe_keyword)
            if count == 0:
                skipped_provinces += 1
                continue
            if count >= 1000 and province.cities:
                regions.extend(province.cities)
            else:
                regions.append(province.short_name)

        logger.info(
            "seven_eleven_amap_regions_planned",
            extra={"search_regions": len(regions), "skipped_provinces": skipped_provinces},
        )
        return regions

    async def _probe_amap_count(
        self, client: httpx.AsyncClient, region: str, keyword: str
    ) -> int:
        response = await client.get(
            AMAP_PLACE_TEXT,
            params={
                "key": self.settings.amap_api_key,
                "keywords": keyword,
                "city": region,
                "types": "060200",
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

    def _amap_keywords(self) -> tuple[str, ...]:
        raw = self.settings.seven_eleven_amap_keywords or self.settings.seven_eleven_amap_keyword
        if raw:
            parts = tuple(keyword.strip() for keyword in raw.split(",") if keyword.strip())
            if parts:
                return tuple(dict.fromkeys(parts))
        return DEFAULT_AMAP_KEYWORDS

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            logger.warning("seven_eleven_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
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
        province = payload.get("province")
        city = payload.get("city")
        district = payload.get("district")
        address = payload.get("address")

        if payload.get("source") == "chengdu_official":
            province, city, district = split_city_full_name(payload.get("city_full_name"))
            city_full_name = payload.get("city_full_name") or ""
            if city_full_name and address and city_full_name not in address:
                address = f"{city_full_name}{address}"

        coordinate_system = CoordinateSystem(payload.get("coordinate_system", CoordinateSystem.GCJ02.value))

        return NormalizedLocation(
            external_id=str(payload["external_id"]),
            name=payload.get("name"),
            address=address,
            province=province,
            city=city,
            district=district,
            postal_code=None,
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            coordinate_system=coordinate_system,
            source_type=payload.get("source", "mixed"),
            source_url=CHENGDU_LOCATOR if payload.get("source") == "chengdu_official" else AMAP_PLACE_TEXT,
            raw_payload=payload.get("raw", payload),
        )
