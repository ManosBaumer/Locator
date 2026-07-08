"""KFC China store-portal HTTP client (order.kfc.com.cn/store-portal)."""

from __future__ import annotations

import json
import math
import uuid
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://order.kfc.com.cn/store-portal"
DEFAULT_REFERER = "https://order.kfc.com.cn/preorder-taro/store"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_SEARCH_KEYWORD = " "
DEFAULT_PAGE_SIZE = 50
# LBS returns ~12–15 nearest stores per call; step must be small enough to overlap in dense cities.
DEFAULT_GRID_SPAN_KM = 35.0
DEFAULT_GRID_STEP_KM = 2.5

# From KFC H5 channel config (businessLine=preorder, client=h5).
DEFAULT_COMMON_PARAMS = {
    "portalType": "WAP",
    "portalSource": "",
    "channelName": "Mobile Web",
    "channelId": "13",
    "brand": "KFC_PRE",
    "business": "preorder",
    "env": "prod",
}

EXCLUDED_GB_CITY_PREFIXES = ("710000", "810000", "820000")


def wrap_request_body(params: dict[str, Any]) -> dict[str, Any]:
    return {
        **params,
        "encodeList": [],
        "isFromCustomerClient": True,
        "secretKey": "kfc",
    }


def grid_points(
    center_lat: float,
    center_lng: float,
    *,
    span_km: float,
    step_km: float,
) -> list[tuple[float, float]]:
    lat_step = step_km / 111.0
    lng_step = step_km / (111.0 * max(math.cos(math.radians(center_lat)), 0.2))
    steps = max(int(span_km / step_km), 1)
    points: list[tuple[float, float]] = []
    for i in range(-steps, steps + 1):
        for j in range(-steps, steps + 1):
            points.append((center_lat + i * lat_step, center_lng + j * lng_step))
    return points


class KfcStorePortalClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        client_version: str = "v6.626(86ae5fef)",
        search_keyword: str = DEFAULT_SEARCH_KEYWORD,
        page_size: int = DEFAULT_PAGE_SIZE,
        grid_span_km: float = DEFAULT_GRID_SPAN_KM,
        grid_step_km: float = DEFAULT_GRID_STEP_KM,
        session_id: str | None = None,
        device_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.client_version = client_version
        self.search_keyword = search_keyword
        self.page_size = page_size
        self.grid_span_km = grid_span_km
        self.grid_step_km = grid_step_km
        self.session_id = session_id or str(uuid.uuid4())
        self.device_id = device_id or str(uuid.uuid4())

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Referer": DEFAULT_REFERER,
            "Origin": "https://order.kfc.com.cn",
        }

    def common_params(self) -> dict[str, Any]:
        return {
            **DEFAULT_COMMON_PARAMS,
            "sessionId": self.session_id,
            "deviceId": self.device_id,
            "clientVersion": self.client_version,
        }

    async def post(self, client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> dict[str, Any]:
        body = wrap_request_body({**self.common_params(), **params})
        response = await client.post(
            f"{self.base_url}{path}",
            headers=self._headers(),
            content=json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected KFC response type: {type(payload).__name__}")
        return payload

    async def fetch_cities(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        payload = await self.post(client, "/api/v2/city/cities", {})
        if payload.get("code") != 0:
            raise RuntimeError(f"KFC cities API error: {payload.get('msg') or payload}")
        data = payload.get("data") or {}
        cities = data.get("allCities") if isinstance(data, dict) else None
        if not isinstance(cities, list):
            raise RuntimeError("KFC cities API returned unexpected payload shape")
        return [city for city in cities if isinstance(city, dict)]

    async def fetch_lbs_stores(
        self,
        client: httpx.AsyncClient,
        *,
        gb_city_code: str,
        latitude: float,
        longitude: float,
    ) -> list[dict[str, Any]]:
        payload = await self.post(
            client,
            "/api/v2/store/searchByLbs",
            {
                "mylat": f"{latitude:.6f}",
                "mylng": f"{longitude:.6f}",
                "gbCityCode": gb_city_code,
                "pageIndex": 1,
                "pageSize": self.page_size,
            },
        )
        if payload.get("code") != 0:
            return []
        data = payload.get("data") or {}
        stores = data.get("stores") if isinstance(data, dict) else None
        if not isinstance(stores, list):
            return []
        return [row for row in stores if isinstance(row, dict)]

    async def fetch_city_stores_by_grid(
        self,
        client: httpx.AsyncClient,
        city: dict[str, Any],
    ) -> list[dict[str, Any]]:
        gb_city_code = str(city.get("gbCityCode") or "")
        if not gb_city_code or gb_city_code.startswith(EXCLUDED_GB_CITY_PREFIXES):
            return []

        try:
            center_lat = float(city.get("latitude"))
            center_lng = float(city.get("longitude"))
        except (TypeError, ValueError):
            return []

        seen_codes: set[str] = set()
        stores: list[dict[str, Any]] = []
        for lat, lng in grid_points(
            center_lat,
            center_lng,
            span_km=self.grid_span_km,
            step_km=self.grid_step_km,
        ):
            page_stores = await self.fetch_lbs_stores(
                client,
                gb_city_code=gb_city_code,
                latitude=lat,
                longitude=lng,
            )
            for row in page_stores:
                if row.get("typeCode") != "H":
                    continue
                if str(row.get("gbCityCode") or "") != gb_city_code:
                    continue
                store_code = row.get("storecode")
                if not store_code or store_code in seen_codes:
                    continue
                seen_codes.add(store_code)
                stores.append(row)
        return stores
