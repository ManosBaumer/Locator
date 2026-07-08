import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

# Public Freshippo (Hema) store directory. Returns {"data": [ {store}, ... ]}.
# Stores carry address components but no coordinates, so the pipeline geocodes
# each address via the configured geocoder (Amap) and normalizes to WGS84.
DEFAULT_SOURCE_URL = (
    "https://hema-infra-center.oss-cn-zhangjiakou.aliyuncs.com/lnc/store.json"
)

# bizStatus values considered as operating stores worth mapping.
ACTIVE_BIZ_STATUS = {"1"}


@register("hema")
class HemaAdapter(BaseChainAdapter):
    chain_slug = "hema"
    adapter_version = "0.2.0"
    source_url = DEFAULT_SOURCE_URL

    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.hema_source_url:
            self.source_url = str(self.settings.hema_source_url)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    async def fetch_raw_data(self) -> Any:
        async with httpx.AsyncClient(
            timeout=30,
            headers={
                "User-Agent": "LocaterBot/0.2 (+https://example.local; location aggregation research)"
            },
            follow_redirects=True,
        ) as client:
            response = await client.get(self.source_url)
            response.raise_for_status()
            # OSS may serve JSON without an application/json content-type.
            return response.json()

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        stores = raw_data.get("data") if isinstance(raw_data, dict) else raw_data
        if not isinstance(stores, list):
            logger.warning("hema_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
            return []

        parsed: list[RawLocation] = []
        for store in stores:
            if not isinstance(store, dict):
                continue
            if store.get("bizStatus") not in ACTIVE_BIZ_STATUS:
                continue
            if not store.get("address") or not store.get("orgResourceCode"):
                continue
            parsed.append(RawLocation(payload=store))
        return parsed

    async def normalize(self, location: RawLocation) -> NormalizedLocation:
        payload = location.payload
        return NormalizedLocation(
            external_id=str(payload["orgResourceCode"]),
            name=payload.get("resourceName") or "盒马",
            address=payload.get("address"),
            province=payload.get("province"),
            city=payload.get("city"),
            district=payload.get("county"),
            postal_code=None,
            # No coordinates in the source; the pipeline enriches via geocoding.
            latitude=None,
            longitude=None,
            coordinate_system=CoordinateSystem.WGS84,
            source_type="json_api",
            source_url=self.source_url,
            raw_payload=payload,
        )
