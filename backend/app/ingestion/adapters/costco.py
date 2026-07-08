import logging
from typing import Any

from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

COSTCO_WEBSITE = "https://www.costco.com.cn/"

# Mainland China warehouse clubs as of early 2026 (7 locations).
# Addresses sourced from Costco China press coverage and store opening announcements.
COSTCO_STORES: list[dict[str, str]] = [
    {
        "external_id": "costco-shanghai-minhang",
        "name": "开市客上海闵行会员店",
        "address": "上海市闵行区朱建路235号",
        "province": "上海市",
        "city": "上海市",
        "district": "闵行区",
    },
    {
        "external_id": "costco-shanghai-pudong",
        "name": "开市客上海浦东会员店",
        "address": "上海市浦东新区康新公路5178号",
        "province": "上海市",
        "city": "上海市",
        "district": "浦东新区",
    },
    {
        "external_id": "costco-suzhou",
        "name": "开市客苏州会员店",
        "address": "江苏省苏州市高新区城际路9号",
        "province": "江苏省",
        "city": "苏州市",
        "district": "虎丘区",
    },
    {
        "external_id": "costco-ningbo",
        "name": "开市客宁波会员店",
        "address": "浙江省宁波市鄞州区首南东路1998号",
        "province": "浙江省",
        "city": "宁波市",
        "district": "鄞州区",
    },
    {
        "external_id": "costco-hangzhou",
        "name": "开市客杭州会员店",
        "address": "浙江省杭州市萧山区鸿达路63号",
        "province": "浙江省",
        "city": "杭州市",
        "district": "萧山区",
    },
    {
        "external_id": "costco-shenzhen",
        "name": "开市客深圳会员店",
        "address": "广东省深圳市龙华区民治街道龙塘社区民达路68号",
        "province": "广东省",
        "city": "深圳市",
        "district": "龙华区",
        # Verified against Amap POI B0J2CLBCYE (星河开市客环球商业中心).
        "latitude": 22.626941,
        "longitude": 114.013758,
        "coordinate_system": CoordinateSystem.GCJ02.value,
    },
    {
        "external_id": "costco-nanjing",
        "name": "开市客南京会员店",
        "address": "江苏省南京市江宁区吉印大道3788号",
        "province": "江苏省",
        "city": "南京市",
        "district": "江宁区",
    },
]


@register("costco")
class CostcoAdapter(BaseChainAdapter):
    """Costco / 开市客 mainland China warehouse clubs.

    Costco operates a small, fixed set of mainland warehouses. Store addresses are
    maintained as a curated static list rather than scraped from a locator API.
    """

    chain_slug = "costco"
    adapter_version = "0.1.0"
    source_url = COSTCO_WEBSITE

    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        stores = [dict(store) for store in COSTCO_STORES]
        logger.info("costco_fetch_complete", extra={"store_count": len(stores)})
        return stores

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            logger.warning("costco_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
            return []

        parsed: list[RawLocation] = []
        for store in raw_data:
            if not isinstance(store, dict):
                continue
            if not store.get("external_id") or not store.get("address"):
                continue
            parsed.append(RawLocation(payload=store))
        return parsed

    async def normalize(self, location: RawLocation) -> NormalizedLocation:
        payload = location.payload
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")
        coordinate_system = payload.get("coordinate_system", CoordinateSystem.WGS84.value)
        if isinstance(coordinate_system, str):
            coordinate_system = CoordinateSystem(coordinate_system)

        return NormalizedLocation(
            external_id=str(payload["external_id"]),
            name=payload.get("name"),
            address=payload.get("address"),
            province=payload.get("province"),
            city=payload.get("city"),
            district=payload.get("district"),
            postal_code=None,
            latitude=float(latitude) if latitude is not None else None,
            longitude=float(longitude) if longitude is not None else None,
            coordinate_system=coordinate_system,
            source_type="static",
            source_url=self.source_url,
            raw_payload=payload,
        )
