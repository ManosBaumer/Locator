import asyncio
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

AMAP_DISTRICT = "https://restapi.amap.com/v3/config/district"

# Mainland-China scope: Amap's "中国" tree includes Taiwan, Hong Kong, and Macau.
EXCLUDED_REGION_PREFIXES = ("台湾", "台灣", "香港", "澳门", "澳門")

# Taiwan place names embedded in addresses (e.g. "台中市西区").
EXCLUDED_REGION_MARKERS = (
    "台湾",
    "台灣",
    "台北",
    "新北",
    "台中",
    "台南",
    "高雄",
    "桃园",
    "桃園",
    "彰化",
    "屏东",
    "屏東",
    "基隆",
    "新竹",
    "苗栗",
    "云林",
    "雲林",
    "嘉义",
    "嘉義",
    "台东",
    "台東",
    "花莲",
    "花蓮",
    "澎湖",
    "金门",
    "金門",
)

# Full SAR names only — avoid matching mainland streets like "香港中路".
EXCLUDED_ADDRESS_MARKERS = (
    "香港特别行政区",
    "澳门特别行政区",
    "澳門特別行政區",
)


def is_excluded_mainland_region(name: str | None) -> bool:
    if not name:
        return False
    return any(name.startswith(prefix) for prefix in EXCLUDED_REGION_PREFIXES)


def is_excluded_mainland_text(value: str | None) -> bool:
    if not value:
        return False
    if is_excluded_mainland_region(value):
        return True
    if any(marker in value for marker in EXCLUDED_REGION_MARKERS):
        return True
    return any(marker in value for marker in EXCLUDED_ADDRESS_MARKERS)


def is_mainland_scope_location(
    *,
    province: str | None = None,
    city: str | None = None,
    district: str | None = None,
    address: str | None = None,
    name: str | None = None,
    longitude: float | None = None,
    latitude: float | None = None,
) -> bool:
    """Return True when a location belongs to the mainland-China dataset scope."""
    for field in (province, city, district):
        if is_excluded_mainland_region(field):
            return False
    for field in (address, name):
        if is_excluded_mainland_text(field):
            return False
    if longitude is not None and latitude is not None:
        if is_excluded_mainland_coordinates(longitude, latitude):
            return False
    return True


def apply_mainland_scope_filter(stmt, location_model):
    """Exclude Taiwan, Hong Kong, and Macau rows from a Location-based query."""
    from sqlalchemy import or_

    for prefix in EXCLUDED_REGION_PREFIXES:
        stmt = stmt.where(
            or_(
                location_model.province.is_(None),
                ~location_model.province.startswith(prefix),
            )
        )
        stmt = stmt.where(
            or_(
                location_model.city.is_(None),
                ~location_model.city.startswith(prefix),
            )
        )
    return stmt


def is_excluded_mainland_coordinates(lng: float, lat: float) -> bool:
    """Reject Taiwan island / Penghu and Macau SAR; keep Fujian coast and Shenzhen."""
    if lng >= 120.0 and 21.9 <= lat <= 25.35:
        return True
    if 119.3 <= lng <= 119.85 and 23.0 <= lat <= 23.8:
        return True
    if 113.50 <= lng <= 113.60 and 22.08 <= lat <= 22.22:
        return True
    return False


@dataclass(frozen=True)
class AmapProvinceRegions:
    short_name: str
    cities: tuple[str, ...]


@dataclass(frozen=True)
class AmapCityCenter:
    province_short: str
    city_name: str
    latitude: float
    longitude: float


def parse_amap_center(center: str | None) -> tuple[float, float] | None:
    if not center or "," not in center:
        return None
    lng_str, lat_str = center.split(",", 1)
    return float(lat_str), float(lng_str)


async def fetch_amap_province_city_tree(
    client: httpx.AsyncClient,
    api_key: str,
    *,
    request_delay_s: float = 0.02,
) -> list[AmapProvinceRegions]:
    """Return each province (short name) with its prefecture-level city names."""
    tree: list[AmapProvinceRegions] = []

    response = await client.get(
        AMAP_DISTRICT,
        params={"key": api_key, "keywords": "中国", "subdistrict": 1, "extensions": "base"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "1":
        raise RuntimeError(f"Amap district lookup failed: {payload.get('info')}")

    province_nodes = payload.get("districts", [{}])[0].get("districts") or []
    for province in province_nodes:
        province_name = province.get("name")
        if not province_name:
            continue
        short_name = _short_region_name(province_name)
        if is_excluded_mainland_region(province_name) or is_excluded_mainland_region(short_name):
            continue

        await asyncio.sleep(request_delay_s)
        city_response = await client.get(
            AMAP_DISTRICT,
            params={
                "key": api_key,
                "keywords": province_name,
                "subdistrict": 1,
                "extensions": "base",
            },
        )
        city_response.raise_for_status()
        city_payload = city_response.json()
        if city_payload.get("status") != "1":
            logger.warning(
                "amap_province_district_skipped",
                extra={"province": province_name, "info": city_payload.get("info")},
            )
            tree.append(AmapProvinceRegions(short_name=short_name, cities=()))
            continue

        cities = tuple(
            city_name
            for city in city_payload.get("districts", [{}])[0].get("districts") or []
            if (city_name := city.get("name"))
        )
        tree.append(AmapProvinceRegions(short_name=short_name, cities=cities))

    logger.info("amap_province_city_tree_loaded", extra={"provinces": len(tree)})
    return tree


async def fetch_amap_city_centers(
    client: httpx.AsyncClient,
    api_key: str,
    *,
    request_delay_s: float = 0.02,
) -> list[AmapCityCenter]:
    """Return prefecture-level city centers for mainland China."""
    centers: list[AmapCityCenter] = []

    response = await client.get(
        AMAP_DISTRICT,
        params={"key": api_key, "keywords": "中国", "subdistrict": 1, "extensions": "base"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "1":
        raise RuntimeError(f"Amap district lookup failed: {payload.get('info')}")

    province_nodes = payload.get("districts", [{}])[0].get("districts") or []
    for province in province_nodes:
        province_name = province.get("name")
        if not province_name:
            continue
        province_short = _short_region_name(province_name)
        if is_excluded_mainland_region(province_name) or is_excluded_mainland_region(province_short):
            continue

        await asyncio.sleep(request_delay_s)
        city_response = await client.get(
            AMAP_DISTRICT,
            params={
                "key": api_key,
                "keywords": province_name,
                "subdistrict": 1,
                "extensions": "base",
            },
        )
        city_response.raise_for_status()
        city_payload = city_response.json()
        if city_payload.get("status") != "1":
            logger.warning(
                "amap_city_centers_skipped",
                extra={"province": province_name, "info": city_payload.get("info")},
            )
            continue

        city_nodes = city_payload.get("districts", [{}])[0].get("districts") or []
        if city_nodes:
            for city in city_nodes:
                city_name = city.get("name")
                coords = parse_amap_center(city.get("center"))
                if not city_name or coords is None:
                    continue
                latitude, longitude = coords
                centers.append(
                    AmapCityCenter(
                        province_short=province_short,
                        city_name=city_name,
                        latitude=latitude,
                        longitude=longitude,
                    )
                )
            continue

        coords = parse_amap_center(province.get("center"))
        if coords is not None:
            latitude, longitude = coords
            centers.append(
                AmapCityCenter(
                    province_short=province_short,
                    city_name=province_name,
                    latitude=latitude,
                    longitude=longitude,
                )
            )

    logger.info("amap_city_centers_loaded", extra={"count": len(centers)})
    return centers


async def fetch_amap_search_regions(
    client: httpx.AsyncClient,
    api_key: str,
    *,
    request_delay_s: float = 0.02,
) -> list[str]:
    """Flat province + city list (legacy helper)."""
    tree = await fetch_amap_province_city_tree(client, api_key, request_delay_s=request_delay_s)
    regions: list[str] = []
    for province in tree:
        regions.append(province.short_name)
        regions.extend(province.cities)
    logger.info("amap_search_regions_loaded", extra={"count": len(regions)})
    return regions


def _short_region_name(name: str) -> str:
    for suffix in ("特别行政区", "自治区", "自治州", "地区", "盟", "省", "市"):
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name
