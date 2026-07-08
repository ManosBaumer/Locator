import json
import logging
import re
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

DEFAULT_STORE_LOCATOR_URL = "https://www.aldi.cn/ourshops/physicalstore/"
USER_AGENT = "LocaterBot/0.1 (+https://example.local; location aggregation research)"
DATA_JSON_MARKER = "data_json:'"


def _loads_data_json_blob(blob: str) -> dict[str, Any] | None:
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def extract_data_json_objects(html: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    pos = 0

    while True:
        start = html.find(DATA_JSON_MARKER, pos)
        if start == -1:
            break

        index = start + len(DATA_JSON_MARKER)
        depth = 0
        end_index: int | None = None

        for offset, char in enumerate(html[index:], start=index):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end_index = offset
                    break

        if end_index is None:
            break

        payload = _loads_data_json_blob(html[index : end_index + 1])
        if payload:
            objects.append(payload)

        pos = end_index + 1

    return objects


def extract_region_from_area(area: object) -> tuple[str | None, str | None, str | None]:
    if not isinstance(area, dict):
        return None, None, None

    district = area.get("name") or (area.get("fields") or {}).get("name")
    city_node = area.get("fields", {}).get("parent") if isinstance(area.get("fields"), dict) else None
    city = city_node.get("name") if isinstance(city_node, dict) else None

    province = None
    if isinstance(city_node, dict):
        province_node = (city_node.get("fields") or {}).get("parent")
        if isinstance(province_node, dict):
            province = province_node.get("name")

    return province, city, district


def parse_address_region(address: str | None) -> tuple[str | None, str | None, str | None]:
    if not address:
        return None, None, None

    match = re.match(
        r"^(?:(.+?省))?(?:(.+?市))?(?:(.+?(?:区|县|市)))?",
        address,
    )
    if not match:
        return None, None, None

    province, city, district = match.groups()
    if address.startswith(("北京市", "上海市", "天津市", "重庆市")):
        municipality = address[:3]
        return municipality, municipality, district

    return province, city, district


def parse_store_record(data: dict[str, Any]) -> dict[str, Any] | None:
    store_id = data.get("id")
    fields = data.get("fields") or {}
    name = fields.get("storesName")
    address = (fields.get("storesAddress") or "").strip()
    if not store_id or not name or not address:
        return None

    province, city, district = extract_region_from_area(fields.get("area"))
    if not province and not city:
        province, city, district = parse_address_region(address)

    if province == "上海":
        province = "上海市"
    if city == "上海":
        city = "上海市"

    hours = None
    start_time = fields.get("startTime")
    end_time = fields.get("endTime")
    if start_time and end_time:
        hours = f"{start_time[:5]}-{end_time[:5]}"

    return {
        "store_id": str(store_id),
        "name": name,
        "address": address,
        "province": province,
        "city": city,
        "district": district,
        "hours": hours,
        "map_url": fields.get("mapUrl") or fields.get("mapLink"),
        "raw": data,
    }


def parse_stores_from_html(html: str) -> list[dict[str, Any]]:
    stores: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for record in extract_data_json_objects(html):
        parsed = parse_store_record(record)
        if parsed is None or parsed["store_id"] in seen_ids:
            continue
        seen_ids.add(parsed["store_id"])
        stores.append(parsed)

    return stores


@register("aldi")
class AldiAdapter(BaseChainAdapter):
    """ALDI / 奥乐齐 mainland China (Shanghai + Jiangsu).

    Store data is embedded in the Nuxt SSR payload on the physical-store page.
    Province/city/district filters are client-side; the full store list is present
    in the initial HTML.
    """

    chain_slug = "aldi"
    adapter_version = "0.1.0"
    source_url = DEFAULT_STORE_LOCATOR_URL

    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.aldi_store_locator_url:
            self.source_url = str(self.settings.aldi_store_locator_url)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=60, headers=headers, follow_redirects=True) as client:
            response = await client.get(self.source_url)
            response.raise_for_status()
            stores = parse_stores_from_html(response.text)

        logger.info(
            "aldi_fetch_complete",
            extra={
                "store_count": len(stores),
                "shanghai": sum(1 for store in stores if (store.get("province") or "").startswith("上海")),
                "jiangsu": sum(1 for store in stores if (store.get("province") or "").startswith("江苏")),
            },
        )
        return stores

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            logger.warning("aldi_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
            return []

        parsed: list[RawLocation] = []
        for store in raw_data:
            if not isinstance(store, dict):
                continue
            if not store.get("store_id") or not store.get("address"):
                continue
            parsed.append(RawLocation(payload=store))
        return parsed

    async def normalize(self, location: RawLocation) -> NormalizedLocation:
        payload = location.payload
        return NormalizedLocation(
            external_id=str(payload["store_id"]),
            name=payload.get("name"),
            address=payload.get("address"),
            province=payload.get("province"),
            city=payload.get("city"),
            district=payload.get("district"),
            postal_code=None,
            latitude=None,
            longitude=None,
            coordinate_system=CoordinateSystem.WGS84,
            source_type="nuxt_ssr",
            source_url=self.source_url,
            raw_payload=payload.get("raw", payload),
        )
