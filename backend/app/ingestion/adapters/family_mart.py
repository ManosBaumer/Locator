import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.amap_regions import is_excluded_mainland_text
from app.ingestion.dedup_keys import dedup_key_for_store, make_content_external_id, pick_richer_store
from app.ingestion.geocode_hints import infer_city_from_address
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

DEFAULT_STORE_LIST_URL = "https://www.yidianlife.com/Family_Mart.html"
USER_AGENT = "LocaterBot/0.1 (+https://example.local; location aggregation research)"
# yidianlife.com exports Excel-as-HTML in GBK; UTF-8 fails on the full document.
PAGE_ENCODINGS = ("gb18030", "gbk", "gb2312", "utf-8")

# Rare GBK characters in the source are often replaced with "?" + an ASCII letter.
_CORRUPT_REPAIRS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"金\?M阁(?=金茗阁)"), ""),
    (re.compile(r"\?I岭"), "下梅林"),
    (re.compile(r"\?蚩谡"), "坦尾"),
    (re.compile(r"五羊\?站"), "五羊邨站"),
    (re.compile(r"沥\?蛘"), "沥滘"),
    (re.compile(r"厦\?蛘"), "厦滘"),
    (re.compile(r"旧唐\?"), "旧塘"),
    (re.compile(r"南\?藻路"), "南蕰藻路"),
    (re.compile(r"\?川路"), "蕰川路"),
    (re.compile(r"镜\?"), "站"),
    (re.compile(r"([\u4e00-\u9fff])\?(?=[A-Z0-9])"), r"\1站"),
    (re.compile(r"\?蛘"), "滘"),
)


def decode_page_text(content: bytes) -> str:
    for encoding in PAGE_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def repair_corrupted_export_text(value: str | None) -> str | None:
    if not value or "?" not in value:
        return value
    repaired = value
    for pattern, replacement in _CORRUPT_REPAIRS:
        repaired = pattern.sub(replacement, repaired)
    return repaired


def _clean_cell(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = repair_corrupted_export_text(value.strip()) or value.strip()
    return cleaned or None


def make_store_external_id(store: dict[str, Any]) -> str:
    return make_content_external_id("fm", store)


def parse_store_table(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    stores_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for row in soup.select("table tr")[1:]:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if len(cells) >= 5:
            province, city, district, name, address = cells[0], cells[1], cells[2], cells[3], cells[4]
        elif len(cells) == 4:
            province, city, name, address = cells
            district = None
        else:
            continue

        province = _clean_cell(province)
        city = _clean_cell(city)
        district = _clean_cell(district)
        name = _clean_cell(name)
        address = _clean_cell(address)

        if not name or not address:
            continue
        if any(
            is_excluded_mainland_text(field)
            for field in (province, city, district, name, address)
        ):
            continue

        record = {
            "province": province or None,
            "city": city or None,
            "district": district or None,
            "name": name,
            "address": address,
        }
        dedup_key = dedup_key_for_store(record)
        existing = stores_by_key.get(dedup_key)
        if existing is None:
            record["external_id"] = make_store_external_id(record)
            stores_by_key[dedup_key] = record
            continue
        merged = pick_richer_store(existing, record)
        merged["external_id"] = make_store_external_id(merged)
        stores_by_key[dedup_key] = merged

    return list(stores_by_key.values())


@register("family-mart")
class FamilyMartAdapter(BaseChainAdapter):
    """FamilyMart / 全家 mainland China.

    familymart.com.cn no longer publishes a store locator; this adapter reads the
    compiled HTML table at yidianlife.com (province / city / district / name / address).
    """

    chain_slug = "family-mart"
    adapter_version = "0.1.5"
    source_url = DEFAULT_STORE_LIST_URL

    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.family_mart_store_list_url:
            self.source_url = str(self.settings.family_mart_store_list_url)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=120, headers=headers, follow_redirects=True) as client:
            response = await client.get(self.source_url)
            response.raise_for_status()
            stores = parse_store_table(decode_page_text(response.content))

        provinces: dict[str, int] = {}
        for store in stores:
            province = store.get("province") or "unknown"
            provinces[province] = provinces.get(province, 0) + 1

        logger.info(
            "family_mart_fetch_complete",
            extra={"store_count": len(stores), "provinces": len(provinces)},
        )
        return stores

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            logger.warning("family_mart_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
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
        name = payload.get("name")
        if name and "全家" not in name and "FamilyMart" not in name:
            name = f"全家{name}"

        address = payload.get("address")
        city = payload.get("city")
        inferred_city = infer_city_from_address(address)
        if inferred_city:
            city = inferred_city

        return NormalizedLocation(
            external_id=str(payload["external_id"]),
            name=name,
            address=address,
            province=payload.get("province"),
            city=city,
            district=payload.get("district"),
            postal_code=None,
            latitude=None,
            longitude=None,
            coordinate_system=CoordinateSystem.WGS84,
            source_type="html_table",
            source_url=self.source_url,
            raw_payload=payload,
        )
