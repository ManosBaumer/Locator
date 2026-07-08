import logging
import re
from typing import Any

from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.adapters.family_mart import repair_corrupted_export_text
from app.ingestion.amap_regions import is_excluded_mainland_text
from app.ingestion.dedup_keys import dedup_key_for_store, make_content_external_id, pick_richer_store
from app.ingestion.fetch import fetch_bytes
from app.ingestion.geocode_hints import infer_city_from_address
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

SPDB_STORE_LIST_URL = "https://ccc.spdb.com.cn/miniSite/2228/cfb6e3d/yh.shtml"
YIDIANLIFE_STORE_LIST_URL = "https://www.yidianlife.com/yh.html"
DEFAULT_STORE_LIST_URL = SPDB_STORE_LIST_URL
USER_AGENT = "LocaterBot/0.1 (+https://example.local; location aggregation research)"
PAGE_ENCODINGS = ("utf-8", "gb18030", "gbk", "gb2312")
YIDIANLIFE_STORE_PATTERN = re.compile(
    r"\{\s*user:\s*'([^']*)',\s*storeName:\s*'([^']*)',\s*address:\s*'([^']*)'\s*\}"
)


def decode_page_text(content: bytes) -> str:
    for encoding in PAGE_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _clean_cell(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = repair_corrupted_export_text(value.strip()) or value.strip()
    return cleaned or None


def _short_region(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = name.strip()
    for suffix in (
        "特别行政区",
        "维吾尔自治区",
        "壮族自治区",
        "回族自治区",
        "自治区",
    ):
        if cleaned.endswith(suffix):
            return cleaned[: -len(suffix)]
    if cleaned.endswith("省") or cleaned.endswith("市"):
        return cleaned[:-1]
    return cleaned


def make_store_external_id(store: dict[str, Any]) -> str:
    return make_content_external_id("yh", store)


def _upsert_parsed_store(
    stores_by_key: dict[tuple[str, str, str, str], dict[str, Any]],
    record: dict[str, Any],
) -> None:
    dedup_key = dedup_key_for_store(record)
    existing = stores_by_key.get(dedup_key)
    if existing is None:
        record["external_id"] = make_store_external_id(record)
        stores_by_key[dedup_key] = record
        return
    merged = pick_richer_store(existing, record)
    merged["external_id"] = make_store_external_id(merged)
    stores_by_key[dedup_key] = merged


def parse_store_table(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    stores_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for row in soup.select("table tr")[1:]:
        cells = [_clean_cell(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        cells = [cell for cell in cells if cell is not None]
        if len(cells) < 4:
            continue

        province, city, name, address = cells[0], cells[1], cells[2], cells[3]
        if not name or not address:
            continue
        if any(
            is_excluded_mainland_text(field)
            for field in (province, city, name, address)
        ):
            continue

        record = {
            "province": _short_region(province),
            "city": _short_region(city),
            "district": None,
            "name": name,
            "address": address,
        }
        _upsert_parsed_store(stores_by_key, record)

    return list(stores_by_key.values())


def parse_yidianlife_embedded_list(html: str) -> list[dict[str, Any]]:
    stores_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for user, store_name, address in YIDIANLIFE_STORE_PATTERN.findall(html):
        name = _clean_cell(user) or _clean_cell(store_name)
        address = _clean_cell(address)
        if not name or not address:
            continue
        if any(is_excluded_mainland_text(field) for field in (name, address)):
            continue

        record = {
            "province": None,
            "city": None,
            "district": None,
            "name": name,
            "address": address,
        }
        _upsert_parsed_store(stores_by_key, record)

    return list(stores_by_key.values())


@register("yonghui")
class YonghuiAdapter(BaseChainAdapter):
    """Yonghui Supermarket / 永辉超市 mainland China.

    Uses the static HTML store table on the SPDB promotional minisite, which is
    more complete than the Vue-driven list at yidianlife.com/yh.html.
    """

    chain_slug = "yonghui"
    adapter_version = "0.1.1"
    source_url = DEFAULT_STORE_LIST_URL

    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.yonghui_store_list_url:
            self.source_url = str(self.settings.yonghui_store_list_url)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT}
        stores: list[dict[str, Any]] = []
        source = "spdb"

        try:
            content = await fetch_bytes(
                SPDB_STORE_LIST_URL,
                headers=headers,
                allow_legacy_ssl=True,
            )
            stores = parse_store_table(decode_page_text(content))
        except Exception as exc:
            logger.warning("yonghui_spdb_fetch_failed", extra={"error": str(exc)})

        if not stores:
            source = "yidianlife"
            content = await fetch_bytes(YIDIANLIFE_STORE_LIST_URL, headers=headers)
            stores = parse_yidianlife_embedded_list(decode_page_text(content))

        provinces: dict[str, int] = {}
        for store in stores:
            province = store.get("province") or "unknown"
            provinces[province] = provinces.get(province, 0) + 1

        logger.info(
            "yonghui_fetch_complete",
            extra={"store_count": len(stores), "provinces": len(provinces), "source": source},
        )
        return stores

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            logger.warning("yonghui_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
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
        if name and "永辉" not in name:
            name = f"永辉{name}"

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
