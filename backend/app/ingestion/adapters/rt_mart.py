import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

DEFAULT_STORE_LOCATOR_URL = (
    "https://www.rt-mart.com.cn/stores/store"
    "?size=8&memLiteClub=9&typeMarket=1&typeSuper=2&typeClub=5"
)
LIST_URL = "https://www.rt-mart.com.cn/stores/store"
PAGE_SIZE = 100
USER_AGENT = "LocaterBot/0.1 (+https://example.local; location aggregation research)"


def parse_store_cards(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    stores: list[dict[str, Any]] = []

    for card in soup.select("div.store-item"):
        link = card.select_one("a[href*='storeId=']")
        if not link:
            continue

        match = re.search(r"storeId=(\d+)", link.get("href", ""))
        if not match:
            continue

        lines = [line.strip() for line in card.get_text("\n", strip=True).split("\n") if line.strip()]
        display_name = next(
            (
                line
                for line in lines
                if "-" in line and not line.startswith(("营业时间", "门店地址", "服务电话", "团购电话", "了解门店"))
            ),
            None,
        )
        address = next((line.removeprefix("门店地址：") for line in lines if line.startswith("门店地址")), None)
        hours = next((line.removeprefix("营业时间：") for line in lines if line.startswith("营业时间")), None)
        phone = next((line.removeprefix("服务电话：") for line in lines if line.startswith("服务电话")), None)

        if not address:
            continue

        stores.append(
            {
                "store_id": match.group(1),
                "display_name": display_name,
                "address": address,
                "hours": hours,
                "phone": phone,
            }
        )

    return stores


def split_city_and_name(display_name: str | None) -> tuple[str | None, str | None]:
    if not display_name or "-" not in display_name:
        return None, display_name

    city, name = display_name.split("-", 1)
    city = city.strip() or None
    name = name.strip() or display_name
    return city, name


@register("rt-mart")
class RtMartAdapter(BaseChainAdapter):
    chain_slug = "rt-mart"
    adapter_version = "0.1.0"
    source_url = DEFAULT_STORE_LOCATOR_URL

    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.rt_mart_store_locator_url:
            self.source_url = str(self.settings.rt_mart_store_locator_url)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT}
        page_size = self.settings.rt_mart_page_size or PAGE_SIZE
        seen_ids: set[str] = set()
        stores: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=60, headers=headers, follow_redirects=True) as client:
            page = 0
            while page < 50:
                params = {
                    "size": page_size,
                    "page": page,
                    "provinceCode": "",
                    "cityCode": "",
                    "storeName": "",
                    "typeMarket": 1,
                    "typeSuper": 2,
                    "typeClub": 5,
                    "memLiteClub": 9,
                }
                response = await client.get(LIST_URL, params=params)
                response.raise_for_status()

                page_stores = parse_store_cards(response.text)
                new_stores = [store for store in page_stores if store["store_id"] not in seen_ids]
                for store in new_stores:
                    seen_ids.add(store["store_id"])
                stores.extend(new_stores)

                logger.info(
                    "rt_mart_page_fetched",
                    extra={
                        "page": page,
                        "page_count": len(page_stores),
                        "new_count": len(new_stores),
                        "total_count": len(stores),
                    },
                )

                if not page_stores:
                    break
                # The API repeats page 0 on page 1; skip duplicate pages instead of stopping.
                if not new_stores:
                    page += 1
                    continue
                page += 1

        logger.info("rt_mart_fetch_complete", extra={"store_count": len(stores)})
        return stores

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            logger.warning("rt_mart_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
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
        city, name = split_city_and_name(payload.get("display_name"))

        return NormalizedLocation(
            external_id=str(payload["store_id"]),
            name=name or payload.get("display_name") or "大润发",
            address=payload.get("address"),
            province=None,
            city=city,
            district=None,
            postal_code=None,
            latitude=None,
            longitude=None,
            coordinate_system=CoordinateSystem.WGS84,
            source_type="html_scrape",
            source_url=self.source_url,
            raw_payload=payload,
        )
