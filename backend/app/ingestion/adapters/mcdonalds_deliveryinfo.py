"""McDonald's mainland China via official disclosure list + per-city API crawl.

1. Loads or scrapes the official deliveryinfo table (~8k stores).
2. Geocodes each city once (cached).
3. Runs parallel bounded ``search_by_point`` grids (small cities first).
4. Stops each city early once every disclosure row for that city is matched.
5. Per-city checkpoint files for fast resume.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.adapters.mcdonalds import (
    McDonaldsDailyQuotaExceeded,
    McDonaldsTransientError,
    RESULTS_PER_QUERY,
    parse_search_by_point_payload,
    parse_store_record,
    subdivide_cell,
    visited_key,
)
from app.ingestion.adapters.mcdonalds_deliveryinfo_checkpoint import (
    McDonaldsDeliveryinfoCheckpoint,
)
from app.ingestion.adapters.mcdonalds_work_queue import McDonaldsWorkQueue
from app.ingestion.dedup_keys import normalize_city, normalize_store_name
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

DELIVERYINFO_URL = "https://www.mcdonalds.com.cn/index/Services/publicinfo/deliveryinfo"
MCDONALDS_STORE_URL = "https://www.mcdonalds.com.cn/store"
DEFAULT_SEARCH_URL = "https://www.mcdonalds.com.cn/ajaxs/search_by_point"
USER_AGENT = "Mozilla/5.0 (compatible; LocaterBot/0.1; store aggregation research)"
AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"

CITY_INITIAL_STEP_DEGREES = 0.04
CITY_DENSE_INITIAL_STEP_DEGREES = 0.02
CITY_MIN_GRID_STEP_DEGREES = 0.01   # ~1.1 km — fine resolution for city-bounded crawl
CITY_BBOX_RADIUS_DEGREES = 0.35
# Non-mega dense cities re-crawl only their urban core (~20 km) at fine resolution.
# A full 0.35 radius makes each city exhaustively grid ~70 km of mostly-empty area
# and pulls in neighbours; sparse far-county stores are already in the DB from the
# nationwide v1.3 crawl, and upserts are additive.
CITY_CORE_RADIUS_DEGREES = 0.18
CITY_DISTRICT_BBOX_RADIUS_DEGREES = 0.10
# Cities at/above this disclosure count skip the plateau early-stop and use the
# fine 0.02 grid. Plateau aborted dense districts in the v1.3 crawl, so every
# dense city must run to grid exhaustion (bounded by the per-city request cap).
LARGE_CITY_DISCLOSURE_THRESHOLD = 40
# Per-city plateau: stop when we have >= target store count and the last window
# of requests discovered nothing new (handles disclosure name-mismatch cases).
# Disabled for large cities — plateau aborts the grid before dense districts finish.
CITY_PLATEAU_WINDOW = 40
# Per-city hard cap = max(this, disclosure_targets * REQUEST_CAP_MULTIPLIER).
CITY_REQUEST_CAP_BASE = 600
CITY_REQUEST_CAP_MULTIPLIER = 150
DISTRICT_REQUEST_CAP_BASE = 400
DISTRICT_REQUEST_CAP_MULTIPLIER = 12
AMAP_POI_TEXT_URL = "https://restapi.amap.com/v3/place/text"
GAP_FILL_CONCURRENCY = 8

# Amap throttling: a startup burst of city + district geocodes trips Amap's QPS
# limit, which previously skipped whole cities. Cap concurrency and retry the
# rate-limit infocodes; do not retry daily-quota infocodes (they never recover).
AMAP_GEOCODE_CONCURRENCY = 3
AMAP_MAX_ATTEMPTS = 6
AMAP_RETRY_BACKOFF_CAP_SECONDS = 8.0
AMAP_RATELIMIT_INFOCODES = {"10019", "10020", "10021", "10022", "10029", "10001"}
AMAP_QUOTA_INFOCODES = {"10003", "10004", "10044", "10045"}
_amap_semaphore = asyncio.Semaphore(AMAP_GEOCODE_CONCURRENCY)

# District-level sub-crawls for mega cities (plateau was aborting before 天河/海珠 finished).
MEGA_CITY_DISTRICTS: dict[str, tuple[str, ...]] = {
    "广州市": (
        "天河区", "海珠区", "越秀区", "荔湾区", "白云区", "番禺区",
        "黄埔区", "南沙区", "花都区", "增城区", "从化区",
    ),
    "深圳市": (
        "福田区", "罗湖区", "南山区", "宝安区", "龙岗区", "龙华区",
        "盐田区", "光明区", "坪山区",
    ),
    "北京市": (
        "东城区", "西城区", "朝阳区", "海淀区", "丰台区", "石景山区",
        "通州区", "昌平区", "大兴区", "顺义区", "房山区",
    ),
    "上海市": (
        "黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区",
        "杨浦区", "闵行区", "宝山区", "嘉定区", "浦东新区", "松江区",
    ),
    "天津市": (
        "和平区", "河东区", "河西区", "南开区", "河北区", "红桥区",
        "东丽区", "西青区", "滨海新区",
    ),
    "重庆市": (
        "渝中区", "江北区", "南岸区", "九龙坡区", "沙坪坝区", "渝北区", "巴南区",
    ),
    "东莞市": ("莞城", "南城", "东城", "万江", "虎门", "长安", "厚街", "塘厦"),
    "佛山市": ("禅城区", "南海区", "顺德区", "三水区", "高明区"),
    "杭州市": (
        "上城区", "拱墅区", "西湖区", "滨江区", "萧山区", "余杭区",
        "临平区", "钱塘区", "富阳区",
    ),
    "武汉市": (
        "江岸区", "江汉区", "硚口区", "汉阳区", "武昌区", "青山区",
        "洪山区", "东西湖区", "江夏区",
    ),
    "成都市": (
        "锦江区", "青羊区", "金牛区", "武侯区", "成华区", "龙泉驿区",
        "新都区", "温江区", "双流区", "郫都区",
    ),
    "南京市": (
        "玄武区", "秦淮区", "建邺区", "鼓楼区", "栖霞区", "雨花台区",
        "江宁区", "浦口区", "六合区",
    ),
    "长沙市": ("芙蓉区", "天心区", "岳麓区", "开福区", "雨花区", "望城区"),
    "苏州市": ("姑苏区", "虎丘区", "吴中区", "相城区", "吴江区"),
    "西安市": (
        "新城区", "碑林区", "莲湖区", "雁塔区", "未央区", "灞桥区", "长安区",
    ),
    "青岛市": (
        "市南区", "市北区", "李沧区", "崂山区", "城阳区", "黄岛区", "即墨区",
    ),
}
HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=15.0)
HTTP_CALL_TIMEOUT_SECONDS = 20.0
HTTP_MAX_ATTEMPTS = 3
# search_by_point gets extra retries: the API intermittently returns transient
# "539 内部错误" server errors that must not abort a multi-hour crawl.
SEARCH_MAX_ATTEMPTS = 6
SEARCH_RETRY_BACKOFF_CAP_SECONDS = 8.0
DAILY_REQUEST_BUDGET = 450_000


@dataclass(frozen=True)
class DisclosureStore:
    city: str
    name: str


def parse_deliveryinfo_page(html: str) -> list[DisclosureStore]:
    soup = BeautifulSoup(html, "html.parser")
    stores: list[DisclosureStore] = []
    for tr in soup.select("table tr")[1:]:
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 2:
            continue
        city = _strip_cell_label(cells[0], "城市")
        name = _strip_cell_label(cells[1], "门店名称")
        if city and name:
            stores.append(DisclosureStore(city=city, name=name))
    return stores


def parse_max_deliveryinfo_page(html: str) -> int | None:
    nums = [int(x) for x in re.findall(r">\s*(\d+)\s*<", html) if int(x) < 10_000]
    return max(nums) if nums else None


def _strip_cell_label(text: str, label: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith(label):
        cleaned = cleaned[len(label) :].strip()
    return cleaned


def disclosure_keys_by_city(disclosure: list[DisclosureStore]) -> dict[str, set[tuple[str, str]]]:
    grouped: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in disclosure:
        grouped[row.city].add((normalize_city(row.city), normalize_store_name(row.name)))
    return dict(grouped)


def api_keys_for_city(stores: dict[str, dict[str, Any]], city: str) -> set[tuple[str, str]]:
    city_norm = normalize_city(city)
    return {
        (city_norm, normalize_store_name(store.get("name")))
        for store in stores.values()
        if normalize_city(store.get("city")) == city_norm
    }


def city_disclosure_complete(
    stores: dict[str, dict[str, Any]],
    city: str,
    pending_keys: set[tuple[str, str]],
) -> bool:
    return pending_keys.issubset(api_keys_for_city(stores, city))


def bbox_radius_for_store_count(store_count: int) -> float:
    if store_count <= 3:
        return 0.12
    if store_count <= 8:
        return 0.18
    if store_count <= 20:
        return 0.25
    return CITY_BBOX_RADIUS_DEGREES


def iter_bounded_grid(
    *,
    min_lat: float,
    max_lat: float,
    min_lng: float,
    max_lng: float,
    step: float,
) -> Iterator[tuple[float, float, float]]:
    latitude = min_lat + step / 2
    while latitude <= max_lat:
        longitude = min_lng + step / 2
        while longitude <= max_lng:
            yield (latitude, longitude, step)
            longitude += step
        latitude += step


def city_should_subdivide(
    rows: list[dict[str, Any]], step: float, *, allow_partial_one_level: bool = False
) -> bool:
    """Subdivision rule for the per-city bounded grid."""
    if step <= CITY_MIN_GRID_STEP_DEGREES:
        return False
    if len(rows) >= RESULTS_PER_QUERY:
        return True
    # One extra subdivision level at the initial step for large-city district crawls.
    if allow_partial_one_level and len(rows) > 0 and step >= CITY_INITIAL_STEP_DEGREES:
        return True
    return False


def unmatched_disclosure_rows(
    disclosure: list[DisclosureStore],
    stores: dict[str, dict[str, Any]],
) -> list[DisclosureStore]:
    api_keys = {
        (normalize_city(s.get("city")), normalize_store_name(s.get("name")))
        for s in stores.values()
    }
    return [
        row
        for row in disclosure
        if (normalize_city(row.city), normalize_store_name(row.name)) not in api_keys
    ]


def match_disclosure_to_api(
    disclosure: list[DisclosureStore],
    api_stores: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    api_keys = {
        (normalize_city(s.get("city")), normalize_store_name(s.get("name")))
        for s in api_stores.values()
    }
    matched = sum(
        1
        for row in disclosure
        if (normalize_city(row.city), normalize_store_name(row.name)) in api_keys
    )
    return matched, len(disclosure) - matched


def _parse_amap_location(entry: dict[str, Any]) -> tuple[float, float] | None:
    location = entry.get("location")
    if not location or "," not in location:
        return None
    lng, lat = (float(part) for part in location.split(",", 1))
    return lat, lng


async def _amap_get(url: str, params: dict[str, str]) -> dict[str, Any] | None:
    """Throttled Amap GET with retry/backoff on QPS rate-limit and transient errors.

    Returns the JSON payload on ``status == "1"``, otherwise ``None``. Daily-quota
    infocodes are not retried (they would never recover within the run).
    """
    last_payload: dict[str, Any] | None = None
    for attempt in range(AMAP_MAX_ATTEMPTS):
        try:
            async with _amap_semaphore:
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            httpx.HTTPStatusError,
        ):
            if attempt + 1 < AMAP_MAX_ATTEMPTS:
                await asyncio.sleep(
                    min(0.5 * (2**attempt), AMAP_RETRY_BACKOFF_CAP_SECONDS)
                    + random.random() * 0.3
                )
            continue

        if payload.get("status") == "1":
            return payload

        infocode = str(payload.get("infocode") or "")
        if infocode in AMAP_QUOTA_INFOCODES:
            logger.warning(
                "amap_daily_quota_exceeded",
                extra={"infocode": infocode, "info": payload.get("info")},
            )
            return None
        if infocode in AMAP_RATELIMIT_INFOCODES:
            last_payload = payload
            if attempt + 1 < AMAP_MAX_ATTEMPTS:
                await asyncio.sleep(
                    min(0.5 * (2**attempt), AMAP_RETRY_BACKOFF_CAP_SECONDS)
                    + random.random() * 0.3
                )
            continue
        # Any other non-success status is not retryable (bad params, no result).
        return None

    if last_payload is not None:
        logger.warning(
            "amap_ratelimited_giving_up",
            extra={"infocode": str(last_payload.get("infocode") or "")},
        )
    return None


async def geocode_city_center_gcj02(city: str, *, api_key: str | None) -> tuple[float, float] | None:
    if not api_key:
        return None
    payload = await _amap_get(AMAP_GEOCODE_URL, {"key": api_key, "address": city, "city": city})
    if payload is None:
        return None
    geocodes = payload.get("geocodes") or []
    if not geocodes:
        return None
    return _parse_amap_location(geocodes[0])


async def geocode_district_center_gcj02(
    city: str, district: str, *, api_key: str | None
) -> tuple[float, float] | None:
    if not api_key:
        return None
    payload = await _amap_get(
        AMAP_GEOCODE_URL, {"key": api_key, "address": district, "city": city}
    )
    if payload is None:
        return None
    geocodes = payload.get("geocodes") or []
    if not geocodes:
        return None
    return _parse_amap_location(geocodes[0])


async def amap_search_poi_gcj02(
    keywords: str, *, city: str, api_key: str | None
) -> tuple[float, float] | None:
    if not api_key:
        return None
    payload = await _amap_get(
        AMAP_POI_TEXT_URL,
        {
            "key": api_key,
            "keywords": keywords,
            "city": city,
            "citylimit": "true",
            "offset": "1",
        },
    )
    if payload is None:
        return None
    pois = payload.get("pois") or []
    if not pois:
        return None
    return _parse_amap_location(pois[0])


@register("mcdonalds_deliveryinfo")
class McDonaldsDeliveryinfoAdapter(BaseChainAdapter):
    chain_slug = "mcdonalds"
    adapter_version = "1.4.0"
    source_url = DELIVERYINFO_URL

    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.mcdonalds_search_url:
            self.search_url = str(self.settings.mcdonalds_search_url)
        else:
            self.search_url = DEFAULT_SEARCH_URL
        self.city_concurrency = max(1, self.settings.mcdonalds_deliveryinfo_city_concurrency)
        self.grid_workers = max(1, self.settings.mcdonalds_deliveryinfo_grid_workers)
        self.page_concurrency = max(1, self.settings.mcdonalds_deliveryinfo_page_concurrency)
        self.max_http_connections = self.city_concurrency * self.grid_workers + 8
        self.cities_filter: set[str] | None = None
        self.cities_min_disclosure: int | None = None
        self.gap_fill_only = False
        self.existing_stores: dict[str, dict[str, Any]] | None = None

    async def fetch_gap_fill_raw_data(self) -> list[dict[str, Any]]:
        """Resolve unmatched disclosure rows via Amap POI + McDonald's search_by_point."""
        if not self.existing_stores:
            raise ValueError("existing_stores required for gap-fill mode")
        logging.getLogger("httpx").setLevel(logging.WARNING)
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": MCDONALDS_STORE_URL,
            "Origin": "https://www.mcdonalds.com.cn",
        }
        checkpoint = McDonaldsDeliveryinfoCheckpoint(
            self.settings.mcdonalds_checkpoint_path,
            adapter_version=self.adapter_version,
        )
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers=headers,
            follow_redirects=True,
        ) as client:
            disclosure = await self._fetch_disclosure_list(client, checkpoint)
            stores = dict(self.existing_stores)
            before_ids = set(stores.keys())
            stores, gap_requests, gap_filled = await self._fill_disclosure_gaps(
                client, disclosure, stores
            )
            new_stores = [stores[k] for k in stores if k not in before_ids]
            matched, unmatched = match_disclosure_to_api(disclosure, stores)
            logger.info(
                "mcdonalds_gap_fill_complete",
                extra={
                    "gap_requests": gap_requests,
                    "gap_filled_rows": gap_filled,
                    "new_store_count": len(new_stores),
                    "matched": matched,
                    "unmatched": unmatched,
                },
            )
            return new_stores

    def load_checkpoint_stores(self) -> list[dict[str, Any]]:
        checkpoint = McDonaldsDeliveryinfoCheckpoint(
            self.settings.mcdonalds_checkpoint_path,
            adapter_version=self.adapter_version,
        )
        stores = checkpoint.load_all_stores()
        if not stores:
            raise ValueError(
                f"No deliveryinfo checkpoint stores under {checkpoint.directory}"
            )
        state = checkpoint.load_state()
        logger.info(
            "mcdonalds_deliveryinfo_checkpoint_stores_loaded",
            extra={
                "store_count": len(stores),
                "completed_cities": len(state.get("completed_cities") or []),
                "request_count": state.get("request_count", 0),
            },
        )
        return list(stores.values())

    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        if self.gap_fill_only:
            return await self.fetch_gap_fill_raw_data()
        logging.getLogger("httpx").setLevel(logging.WARNING)
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": MCDONALDS_STORE_URL,
            "Origin": "https://www.mcdonalds.com.cn",
        }
        checkpoint = McDonaldsDeliveryinfoCheckpoint(
            self.settings.mcdonalds_checkpoint_path,
            adapter_version=self.adapter_version,
        )
        if self.settings.mcdonalds_reset_checkpoint and checkpoint.exists:
            checkpoint.clear()

        state = checkpoint.load_state()
        completed_cities: set[str] = set(state.get("completed_cities") or [])
        request_count = int(state.get("request_count") or 0)
        stores = checkpoint.load_all_stores()

        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers=headers,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=self.max_http_connections,
                max_keepalive_connections=self.max_http_connections - 4,
            ),
        ) as client:
            disclosure = await self._fetch_disclosure_list(client, checkpoint)
            keys_by_city = disclosure_keys_by_city(disclosure)

            # --cities-min-disclosure: build the re-crawl filter from the manifest
            # so dense cities can be targeted without listing every name on the CLI.
            if self.cities_min_disclosure is not None:
                dense = {
                    city
                    for city, keys in keys_by_city.items()
                    if len(keys) >= self.cities_min_disclosure
                }
                self.cities_filter = (
                    dense if self.cities_filter is None else self.cities_filter | dense
                )

            logger.info(
                "mcdonalds_disclosure_loaded",
                extra={
                    "store_count": len(disclosure),
                    "city_count": len(keys_by_city),
                    "resumed_completed_cities": len(completed_cities),
                    "resumed_store_count": len(stores),
                    "city_concurrency": self.city_concurrency,
                    "grid_workers": self.grid_workers,
                    "cities_filter_count": (
                        len(self.cities_filter) if self.cities_filter else None
                    ),
                },
            )

            pending_cities = sorted(
                (
                    city
                    for city in keys_by_city
                    if city not in completed_cities
                    or (self.cities_filter and city in self.cities_filter)
                ),
                key=lambda city: len(keys_by_city[city]),
            )
            if self.cities_filter:
                pending_cities = [c for c in pending_cities if c in self.cities_filter]
                completed_cities -= self.cities_filter
            stores_lock = asyncio.Lock()
            budget_lock = asyncio.Lock()
            checkpoint_lock = asyncio.Lock()
            geocode_lock = asyncio.Lock()
            city_semaphore = asyncio.Semaphore(self.city_concurrency)

            async def persist_state() -> None:
                async with checkpoint_lock:
                    await asyncio.to_thread(
                        checkpoint.save_state,
                        completed_cities=list(completed_cities),
                        request_count=request_count,
                    )

            async def resolve_city_center(city: str) -> tuple[float, float] | None:
                cached = checkpoint.load_geocode(city)
                if cached is not None:
                    return cached
                center = await geocode_city_center_gcj02(
                    city, api_key=self.settings.amap_api_key or None
                )
                if center is None:
                    return None
                lat, lng = center
                async with geocode_lock:
                    cached = checkpoint.load_geocode(city)
                    if cached is not None:
                        return cached
                    await asyncio.to_thread(checkpoint.save_geocode, city, lat, lng)
                return lat, lng

            async def crawl_one_city(city: str) -> None:
                nonlocal request_count
                async with city_semaphore:
                    async with budget_lock:
                        if request_count >= DAILY_REQUEST_BUDGET:
                            return
                        budget_remaining = DAILY_REQUEST_BUDGET - request_count

                    center = await resolve_city_center(city)
                    if center is None:
                        logger.warning("mcdonalds_city_center_missing", extra={"city": city})
                        async with stores_lock:
                            completed_cities.add(city)
                        await persist_state()
                        return

                    city_lat, city_lng = center
                    targets = len(keys_by_city[city])
                    is_large = targets >= LARGE_CITY_DISCLOSURE_THRESHOLD
                    districts = MEGA_CITY_DISTRICTS.get(city, ())

                    city_stores: dict[str, dict[str, Any]] = {}
                    city_requests = 0
                    stopped_early = False
                    stop_reason = "exhausted"

                    if districts:
                        district_count = len(districts)
                        district_cap = max(
                            DISTRICT_REQUEST_CAP_BASE,
                            targets
                            * DISTRICT_REQUEST_CAP_MULTIPLIER
                            // max(district_count, 1),
                        )
                        for district in districts:
                            async with budget_lock:
                                if request_count + city_requests >= DAILY_REQUEST_BUDGET:
                                    break
                                budget_remaining = (
                                    DAILY_REQUEST_BUDGET - request_count - city_requests
                                )
                            dcenter = await geocode_district_center_gcj02(
                                city,
                                district,
                                api_key=self.settings.amap_api_key or None,
                            )
                            if dcenter is None:
                                continue
                            d_lat, d_lng = dcenter
                            sub_stores, sub_requests, _, district_stop = await self._crawl_city_bbox(
                                client,
                                city=city,
                                pending_keys=keys_by_city[city],
                                min_lat=d_lat - CITY_DISTRICT_BBOX_RADIUS_DEGREES,
                                max_lat=d_lat + CITY_DISTRICT_BBOX_RADIUS_DEGREES,
                                min_lng=d_lng - CITY_DISTRICT_BBOX_RADIUS_DEGREES,
                                max_lng=d_lng + CITY_DISTRICT_BBOX_RADIUS_DEGREES,
                                budget_remaining=budget_remaining,
                                grid_workers=self.grid_workers,
                                initial_step=CITY_DENSE_INITIAL_STEP_DEGREES,
                                enable_plateau=False,
                                allow_partial_one_level=True,
                                request_cap_override=min(budget_remaining, district_cap),
                            )
                            city_stores.update(sub_stores)
                            city_requests += sub_requests
                            logger.info(
                                "mcdonalds_district_crawl_complete",
                                extra={
                                    "city": city,
                                    "district": district,
                                    "search_requests": sub_requests,
                                    "store_count": len(sub_stores),
                                    "stop_reason": district_stop,
                                    "city_store_count": len(city_stores),
                                },
                            )
                            if city_disclosure_complete(
                                city_stores, city, keys_by_city[city]
                            ):
                                stopped_early = True
                                stop_reason = "names_matched"
                                break

                    if not city_disclosure_complete(city_stores, city, keys_by_city[city]):
                        async with budget_lock:
                            if request_count + city_requests >= DAILY_REQUEST_BUDGET:
                                pass
                            else:
                                budget_remaining = (
                                    DAILY_REQUEST_BUDGET - request_count - city_requests
                                )
                                if is_large:
                                    # Bounded urban-core crawl at fine resolution; no
                                    # plateau so dense districts are fully covered.
                                    radius = CITY_CORE_RADIUS_DEGREES
                                    step = CITY_DENSE_INITIAL_STEP_DEGREES
                                else:
                                    radius = bbox_radius_for_store_count(targets)
                                    step = CITY_INITIAL_STEP_DEGREES
                                sub_stores, sub_requests, stopped_early, stop_reason = (
                                    await self._crawl_city_bbox(
                                        client,
                                        city=city,
                                        pending_keys=keys_by_city[city],
                                        min_lat=city_lat - radius,
                                        max_lat=city_lat + radius,
                                        min_lng=city_lng - radius,
                                        max_lng=city_lng + radius,
                                        budget_remaining=budget_remaining,
                                        grid_workers=self.grid_workers,
                                        initial_step=step,
                                        enable_plateau=not is_large,
                                    )
                                )
                                city_stores.update(sub_stores)
                                city_requests += sub_requests

                    async with budget_lock:
                        request_count += city_requests
                    async with stores_lock:
                        stores.update(city_stores)
                        completed_cities.add(city)
                    async with checkpoint_lock:
                        await asyncio.to_thread(
                            checkpoint.save_city,
                            city,
                            city_stores,
                            search_requests=city_requests,
                            stopped_early=stopped_early,
                        )
                        await asyncio.to_thread(
                            checkpoint.save_state,
                            completed_cities=list(completed_cities),
                            request_count=request_count,
                        )
                    logger.info(
                        "mcdonalds_city_crawl_complete",
                        extra={
                            "city": city,
                            "search_requests": city_requests,
                            "store_count": len(city_stores),
                            "stopped_early": stopped_early,
                            "stop_reason": stop_reason,
                            "disclosure_targets": len(keys_by_city[city]),
                            "total_store_count": len(stores),
                        },
                    )

            try:
                await asyncio.gather(*(crawl_one_city(city) for city in pending_cities))
            except McDonaldsDailyQuotaExceeded:
                await persist_state()
                raise

            # For a targeted --cities run, only the filtered cities were crawled,
            # so restrict gap-fill to those cities. Otherwise Amap POI lookups would
            # fire for every other (un-crawled) city's "unmatched" rows.
            gap_disclosure = disclosure
            if self.cities_filter:
                gap_disclosure = [
                    row for row in disclosure if row.city in self.cities_filter
                ]

            stores, gap_requests, gap_filled = await self._fill_disclosure_gaps(
                client, gap_disclosure, stores
            )
            request_count += gap_requests
            matched, unmatched = match_disclosure_to_api(gap_disclosure, stores)
            logger.info(
                "mcdonalds_disclosure_match_summary",
                extra={
                    "disclosure_count": len(gap_disclosure),
                    "api_store_count": len(stores),
                    "matched": matched,
                    "unmatched": unmatched,
                    "search_requests": request_count,
                    "gap_fill_requests": gap_requests,
                    "gap_fill_rows": gap_filled,
                    "cities_filter": sorted(self.cities_filter)
                    if self.cities_filter
                    else None,
                },
            )
            if not self.cities_filter:
                checkpoint.clear()
            return list(stores.values())

    async def _fetch_disclosure_list(
        self,
        client: httpx.AsyncClient,
        checkpoint: McDonaldsDeliveryinfoCheckpoint,
    ) -> list[DisclosureStore]:
        cached = checkpoint.load_manifest()
        if cached is not None:
            logger.info(
                "mcdonalds_disclosure_manifest_cache_hit",
                extra={"store_count": len(cached)},
            )
            return [DisclosureStore(city=row["city"], name=row["name"]) for row in cached]

        first_html = (await client.get(DELIVERYINFO_URL, params={"page": 1})).text
        max_page = parse_max_deliveryinfo_page(first_html) or 1
        stores = parse_deliveryinfo_page(first_html)
        pages = list(range(2, max_page + 1))

        async def fetch_page(page: int) -> list[DisclosureStore]:
            html = (await client.get(DELIVERYINFO_URL, params={"page": page})).text
            return parse_deliveryinfo_page(html)

        semaphore = asyncio.Semaphore(self.page_concurrency)

        async def bounded_fetch(page: int) -> list[DisclosureStore]:
            async with semaphore:
                return await fetch_page(page)

        for batch_start in range(0, len(pages), 64):
            batch = pages[batch_start : batch_start + 64]
            results = await asyncio.gather(*(bounded_fetch(page) for page in batch))
            for page_stores in results:
                stores.extend(page_stores)

        seen: set[tuple[str, str]] = set()
        unique: list[DisclosureStore] = []
        for row in stores:
            key = (row.city, row.name)
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)

        await asyncio.to_thread(
            checkpoint.save_manifest,
            [{"city": row.city, "name": row.name} for row in unique],
        )
        return unique

    async def _fill_disclosure_gaps(
        self,
        client: httpx.AsyncClient,
        disclosure: list[DisclosureStore],
        stores: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], int, int]:
        """Resolve unmatched disclosure rows via Amap POI lookup + search_by_point."""
        api_key = self.settings.amap_api_key or None
        if not api_key:
            logger.warning("mcdonalds_gap_fill_skipped_no_amap_key")
            return stores, 0, 0

        pending = unmatched_disclosure_rows(disclosure, stores)
        if not pending:
            return stores, 0, 0

        logger.info("mcdonalds_gap_fill_start", extra={"unmatched_count": len(pending)})
        semaphore = asyncio.Semaphore(GAP_FILL_CONCURRENCY)
        request_count = 0
        filled_rows = 0
        stores_lock = asyncio.Lock()
        count_lock = asyncio.Lock()

        async def fill_one(row: DisclosureStore) -> bool:
            nonlocal request_count, filled_rows
            row_key = (normalize_city(row.city), normalize_store_name(row.name))
            keywords = [row.name]
            if "麦当劳" not in row.name:
                keywords.append(f"麦当劳{row.name}")

            for keyword in keywords:
                poi = await amap_search_poi_gcj02(keyword, city=row.city, api_key=api_key)
                if poi is None:
                    continue
                lat, lng = poi
                rows = await self._search_by_point(client, lat, lng)
                async with count_lock:
                    request_count += 1
                async with stores_lock:
                    for api_row in rows:
                        parsed = parse_store_record(api_row)
                        if parsed is not None:
                            stores[parsed["external_id"]] = parsed
                    if row_key in {
                        (normalize_city(s.get("city")), normalize_store_name(s.get("name")))
                        for s in stores.values()
                    }:
                        filled_rows += 1
                        return True
            return False

        async def bounded_fill(row: DisclosureStore) -> None:
            async with semaphore:
                await fill_one(row)

        await asyncio.gather(*(bounded_fill(row) for row in pending))
        logger.info(
            "mcdonalds_gap_fill_done",
            extra={
                "attempted": len(pending),
                "filled_rows": filled_rows,
                "requests": request_count,
            },
        )
        return stores, request_count, filled_rows

    async def _crawl_city_bbox(
        self,
        client: httpx.AsyncClient,
        *,
        city: str,
        pending_keys: set[tuple[str, str]],
        min_lat: float,
        max_lat: float,
        min_lng: float,
        max_lng: float,
        budget_remaining: int,
        grid_workers: int,
        initial_step: float = CITY_INITIAL_STEP_DEGREES,
        enable_plateau: bool = True,
        allow_partial_one_level: bool = False,
        request_cap_override: int | None = None,
    ) -> tuple[dict[str, dict[str, Any]], int, bool, str]:
        stores: dict[str, dict[str, Any]] = {}
        visited: set[tuple[float, float]] = set()
        visited_lock = asyncio.Lock()
        stores_lock = asyncio.Lock()
        count_lock = asyncio.Lock()
        stop_event = asyncio.Event()

        # All mutable scalars tracked under count_lock.
        request_count = 0
        city_store_count = 0
        plateau_window_reqs = 0
        plateau_window_new = 0
        stopped_early = False
        stop_reason: str = "exhausted"

        # Per-city hard cap: generous enough for large metros, tight for small cities.
        city_request_cap = min(
            budget_remaining,
            request_cap_override
            if request_cap_override is not None
            else max(CITY_REQUEST_CAP_BASE, len(pending_keys) * CITY_REQUEST_CAP_MULTIPLIER),
        )

        work_queue = McDonaldsWorkQueue()
        await work_queue.put_many(
            iter_bounded_grid(
                min_lat=min_lat,
                max_lat=max_lat,
                min_lng=min_lng,
                max_lng=max_lng,
                step=initial_step,
            )
        )

        async def trigger_stop(reason: str) -> None:
            nonlocal stopped_early, stop_reason
            stopped_early = True
            stop_reason = reason
            stop_event.set()
            await work_queue.abort(grid_workers)

        async def process_cell(latitude: float, longitude: float, step: float) -> None:
            nonlocal request_count, city_store_count, plateau_window_reqs, plateau_window_new
            if stop_event.is_set():
                return

            point_key = visited_key(latitude, longitude)
            async with visited_lock:
                if point_key in visited:
                    return
                visited.add(point_key)

            # Pre-check budget and city cap before the HTTP call.
            async with count_lock:
                if request_count >= budget_remaining:
                    raise McDonaldsDailyQuotaExceeded(
                        f"Stopping at {DAILY_REQUEST_BUDGET} requests (daily McDonald's budget)"
                    )
                if request_count >= city_request_cap:
                    return

            rows = await self._search_by_point(client, latitude, longitude)
            if stop_event.is_set():
                return

            # Update stores and count atomically under stores_lock.
            async with stores_lock:
                before = len(stores)
                for row in rows:
                    parsed = parse_store_record(row)
                    if parsed is not None:
                        stores[parsed["external_id"]] = parsed
                new_in_cell = len(stores) - before

                # Condition 1: all disclosure names matched.
                if city_disclosure_complete(stores, city, pending_keys):
                    async with count_lock:
                        request_count += 1
                    await trigger_stop("names_matched")
                    return

            # Update counters and check plateau under count_lock.
            do_plateau_check = False
            plateau_new_snap = 0
            local_store_count = 0
            local_req_count = 0
            async with count_lock:
                request_count += 1
                city_store_count += new_in_cell
                plateau_window_reqs += 1
                plateau_window_new += new_in_cell
                local_store_count = city_store_count
                local_req_count = request_count
                if plateau_window_reqs >= CITY_PLATEAU_WINDOW:
                    do_plateau_check = True
                    plateau_new_snap = plateau_window_new
                    plateau_window_reqs = 0
                    plateau_window_new = 0

            if stop_event.is_set():
                return

            # Condition 2: plateau — found >= targets, nothing new in window.
            if (
                enable_plateau
                and do_plateau_check
                and local_store_count >= len(pending_keys)
                and plateau_new_snap == 0
            ):
                await trigger_stop("plateau")
                return

            # Condition 3: per-city request cap hit.
            if local_req_count >= city_request_cap:
                await trigger_stop("cap")
                return

            if city_should_subdivide(
                rows, step, allow_partial_one_level=allow_partial_one_level
            ):
                await work_queue.put_many(subdivide_cell(latitude, longitude, step))

        async def worker() -> None:
            while True:
                item = await work_queue.get()
                try:
                    if item is None:
                        return
                    await process_cell(*item)
                finally:
                    await work_queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(grid_workers)]
        try:
            await work_queue.join()
            for _ in workers:
                await work_queue.put_sentinel()
            await work_queue.join()
            await asyncio.gather(*workers)
        except McDonaldsDailyQuotaExceeded:
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            raise

        return stores, request_count, stopped_early, stop_reason

    async def _search_by_point(
        self, client: httpx.AsyncClient, latitude: float, longitude: float
    ) -> list[dict[str, Any]]:
        last_exc: Exception | None = None
        for attempt in range(SEARCH_MAX_ATTEMPTS):
            try:
                response = await asyncio.wait_for(
                    client.post(
                        self.search_url,
                        data={"point": f"{latitude},{longitude}"},
                    ),
                    timeout=HTTP_CALL_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                return parse_search_by_point_payload(response.json())
            except (
                asyncio.TimeoutError,
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.RemoteProtocolError,
                httpx.HTTPStatusError,
                McDonaldsTransientError,
            ) as exc:
                last_exc = exc
                if attempt + 1 < SEARCH_MAX_ATTEMPTS:
                    await asyncio.sleep(
                        min(0.5 * (2**attempt), SEARCH_RETRY_BACKOFF_CAP_SECONDS)
                    )
        if last_exc is not None:
            # Skip this cell rather than aborting the crawl; a persistent error on
            # one point loses at most ~10 nearby stores, recoverable by gap-fill.
            logger.warning(
                "mcdonalds_search_by_point_failed",
                extra={
                    "latitude": latitude,
                    "longitude": longitude,
                    "error": type(last_exc).__name__,
                    "detail": str(last_exc)[:160],
                },
            )
        return []

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            return []
        return [RawLocation(payload=store) for store in raw_data if isinstance(store, dict)]

    async def normalize(self, location: RawLocation) -> NormalizedLocation:
        payload = location.payload
        coordinate_system = CoordinateSystem(
            payload.get("coordinate_system", CoordinateSystem.GCJ02.value)
        )
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
            source_type="mcdonalds_deliveryinfo_city_grid",
            source_url=self.source_url,
            raw_payload=payload.get("raw", payload),
        )
