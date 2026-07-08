import asyncio
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.adapters.mcdonalds_checkpoint import McDonaldsGridCheckpoint
from app.ingestion.adapters.mcdonalds_work_queue import McDonaldsWorkQueue
from app.ingestion.amap_regions import (
    is_excluded_mainland_coordinates,
    is_excluded_mainland_region,
)
from app.ingestion.registry import register
from app.models.enums import CoordinateSystem
from app.schemas.poi import NormalizedLocation, RawLocation

logger = logging.getLogger(__name__)

MCDONALDS_STORE_URL = "https://www.mcdonalds.com.cn/store"
DEFAULT_SEARCH_URL = "https://www.mcdonalds.com.cn/ajaxs/search_by_point"
USER_AGENT = "Mozilla/5.0 (compatible; LocaterBot/0.1; store aggregation research)"

# search_by_point returns at most 10 nearest stores per point. We tile mainland China
# with an adaptive grid: coarse initial pass, then quad subdivide to full resolution.
RESULTS_PER_QUERY = 10
# ~11 km cells at China's latitude — fast pass over sparsely covered west/north.
INITIAL_GRID_STEP_DEGREES = 0.10
# ~440 m cells — dense enough that 10-result caps cannot hide nearby stores.
MIN_GRID_STEP_DEGREES = 0.004
# Large empty cells still subdivide so dense pockets off the cell center get queried.
EMPTY_CELL_SUBDIVIDE_MIN_STEP = 0.05
# Mainland China bounding box (generous; HK/Macau/Taiwan grid points are skipped).
MAINLAND_MIN_LAT = 18.15
MAINLAND_MAX_LAT = 53.55
MAINLAND_MIN_LNG = 73.66
MAINLAND_MAX_LNG = 134.77
# Round visited keys to ~11 m so overlapping subdivisions are not re-queried.
VISITED_PRECISION = 4
# McDonald's shared backend key has a ~500k/day cap; stop below that so we can resume.
DAILY_REQUEST_BUDGET = 450_000
# Moderate concurrency — high burst rates contributed to site-wide outages.
SEARCH_CONCURRENCY = 4
CHECKPOINT_INTERVAL = 1_000
QUOTA_EXCEEDED_STATUS = 121
# Stop when a rolling window adds fewer than this many new stores — only after the queue
# is drained, so we never abandon tens of thousands of unqueried cells mid-crawl.
PLATEAU_WINDOW_REQUESTS = 5_000
PLATEAU_MAX_NEW_STORES_IN_WINDOW = 20
PLATEAU_MAX_QUEUE_SIZE = 0
# Avoid stopping during the sparse early pass before the mainland set is mostly covered.
MIN_STORES_BEFORE_PLATEAU = 1_000
HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=10.0)
HTTP_MAX_ATTEMPTS = 3
HTTP_CALL_TIMEOUT_SECONDS = 25.0
WORKER_SHUTDOWN_TIMEOUT_SECONDS = 120
HEARTBEAT_INTERVAL_SECONDS = 60
STALL_RECOVERY_SECONDS = 180
LARGE_QUEUE_CHECKPOINT_INTERVAL = 5_000


class McDonaldsDailyQuotaExceeded(RuntimeError):
    """Raised when McDonald's search_by_point returns a daily quota error."""


class McDonaldsTransientError(RuntimeError):
    """Raised on a retryable McDonald's API error (e.g. status 539 internal error)."""


@dataclass
class PlateauTracker:
    """Rolling window: stop when sparse areas yield almost no new stores."""

    window_requests: int = 0
    window_new_stores: int = 0

    def record_request(
        self, new_stores_added: int, store_count: int, queue_size: int
    ) -> tuple[bool, int]:
        self.window_requests += 1
        self.window_new_stores += new_stores_added
        if self.window_requests < PLATEAU_WINDOW_REQUESTS:
            return False, self.window_new_stores
        window_new_stores = self.window_new_stores
        should_stop = (
            store_count >= MIN_STORES_BEFORE_PLATEAU
            and window_new_stores < PLATEAU_MAX_NEW_STORES_IN_WINDOW
            and queue_size <= PLATEAU_MAX_QUEUE_SIZE
        )
        self.window_requests = 0
        self.window_new_stores = 0
        return should_stop, window_new_stores


def should_stop_on_plateau(requests_without_new: int, store_count: int) -> bool:
    """Legacy consecutive-zero counter; kept for unit tests."""
    return (
        store_count >= MIN_STORES_BEFORE_PLATEAU
        and requests_without_new >= PLATEAU_WINDOW_REQUESTS
    )


def parse_search_by_point_payload(payload: Any) -> list[dict[str, Any]]:
    """Parse search_by_point JSON, raising on quota or unexpected error payloads."""
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected McDonald's response type: {type(payload).__name__}")

    message = payload.get("message")
    if isinstance(message, dict):
        status = message.get("status")
        if status == QUOTA_EXCEEDED_STATUS:
            raise McDonaldsDailyQuotaExceeded(message.get("message") or "Daily API quota exceeded")
        if status not in (None, 0, 200, "0", "200"):
            # Server-side errors (e.g. 539 "内部错误，请稍后重试") are transient and
            # must be retried rather than aborting a multi-hour crawl.
            raise McDonaldsTransientError(
                f"McDonald's API error status {status}: {message.get('message')}"
            )

    rows = payload.get("data") or []
    if not isinstance(rows, list):
        raise ValueError("McDonald's response data is not a list")
    return [row for row in rows if isinstance(row, dict)]


def parse_store_record(record: dict[str, Any]) -> dict[str, Any] | None:
    store_id = record.get("id")
    location = record.get("location") or {}
    latitude = location.get("lat")
    longitude = location.get("lng")
    if not store_id or latitude is None or longitude is None:
        return None

    province = record.get("province")
    city = record.get("city")
    if is_excluded_mainland_region(province) or is_excluded_mainland_region(city):
        return None
    if is_excluded_mainland_coordinates(float(longitude), float(latitude)):
        return None

    address = (record.get("address") or "").strip() or None
    return {
        "external_id": f"mcd-{store_id}",
        "name": record.get("title"),
        "address": address,
        "province": province,
        "city": city,
        "district": record.get("district"),
        "phone": record.get("tel") or None,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "coordinate_system": CoordinateSystem.GCJ02.value,
        "raw": record,
    }


def is_excluded_grid_point(latitude: float, longitude: float) -> bool:
    """Skip query points in Taiwan, Macau, and other out-of-scope coordinates."""
    return is_excluded_mainland_coordinates(longitude, latitude)


def iter_initial_grid(
    *,
    min_lat: float = MAINLAND_MIN_LAT,
    max_lat: float = MAINLAND_MAX_LAT,
    min_lng: float = MAINLAND_MIN_LNG,
    max_lng: float = MAINLAND_MAX_LNG,
    step: float = INITIAL_GRID_STEP_DEGREES,
) -> Iterator[tuple[float, float, float]]:
    """Yield cell centers for the coarse mainland grid (lat, lng, step)."""
    latitude = min_lat + step / 2
    while latitude <= max_lat:
        longitude = min_lng + step / 2
        while longitude <= max_lng:
            if not is_excluded_grid_point(latitude, longitude):
                yield (latitude, longitude, step)
            longitude += step
        latitude += step


def subdivide_cell(latitude: float, longitude: float, step: float) -> list[tuple[float, float, float]]:
    """Split a saturated cell into four quadrant children at half the step size."""
    quarter = step / 4.0
    half_step = step / 2.0
    children: list[tuple[float, float, float]] = []
    for dlat in (-quarter, quarter):
        for dlng in (-quarter, quarter):
            child_lat = latitude + dlat
            child_lng = longitude + dlng
            if is_excluded_grid_point(child_lat, child_lng):
                continue
            children.append((child_lat, child_lng, half_step))
    return children


def checkpoint_interval_for(queue_size: int) -> int:
    if queue_size > 200_000:
        return LARGE_QUEUE_CHECKPOINT_INTERVAL
    if queue_size > 100_000:
        return 2_500
    return CHECKPOINT_INTERVAL


def should_subdivide(rows: list[dict[str, Any]], step: float) -> bool:
    """Decide whether to quad-split a grid cell.

    Subdivide when saturated (10 results), when any store was found (partial hits
    must drill down — otherwise dense districts like Tianhe are skipped), or when a
    large cell returned zero results (center may be off a dense pocket).
    """
    if step <= MIN_GRID_STEP_DEGREES:
        return False
    if len(rows) >= RESULTS_PER_QUERY or len(rows) > 0:
        return True
    return len(rows) == 0 and step > EMPTY_CELL_SUBDIVIDE_MIN_STEP


def visited_key(latitude: float, longitude: float) -> tuple[float, float]:
    return (round(latitude, VISITED_PRECISION), round(longitude, VISITED_PRECISION))


@register("mcdonalds")
class McDonaldsAdapter(BaseChainAdapter):
    """McDonald's / 麦当劳 mainland China.

    Store locations come from the official McDonald's China store locator endpoint
    (``/ajaxs/search_by_point``). The API returns at most 10 nearest stores per
    ``lat,lng`` query, so coverage uses a full adaptive grid over mainland China:
    a coarse initial lattice plus quad subdivisions until full resolution.
    Progress is checkpointed to SQLite so long crawls can resume after interruption.
    """

    chain_slug = "mcdonalds"
    adapter_version = "0.3.3"
    source_url = MCDONALDS_STORE_URL

    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.mcdonalds_search_url:
            self.search_url = str(self.settings.mcdonalds_search_url)
        else:
            self.search_url = DEFAULT_SEARCH_URL

    def load_checkpoint_stores(self) -> list[dict[str, Any]]:
        checkpoint = McDonaldsGridCheckpoint(
            self.settings.mcdonalds_checkpoint_path,
            adapter_version=self.adapter_version,
        )
        state = checkpoint.load()
        if state is None:
            raise ValueError(
                f"No McDonald's checkpoint at {checkpoint.path} (or adapter version mismatch)"
            )
        logger.info(
            "mcdonalds_checkpoint_stores_loaded",
            extra={
                "store_count": len(state.stores),
                "request_count": state.request_count,
                "queue_size": len(state.queue),
            },
        )
        return list(state.stores.values())

    async def fetch_raw_data(self) -> list[dict[str, Any]]:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": MCDONALDS_STORE_URL,
            "Origin": "https://www.mcdonalds.com.cn",
        }

        checkpoint = McDonaldsGridCheckpoint(
            self.settings.mcdonalds_checkpoint_path,
            adapter_version=self.adapter_version,
        )
        if self.settings.mcdonalds_reset_checkpoint and checkpoint.exists:
            checkpoint.clear()
            checkpoint = McDonaldsGridCheckpoint(
                self.settings.mcdonalds_checkpoint_path,
                adapter_version=self.adapter_version,
            )

        saved = checkpoint.load()
        if checkpoint.exists and saved is None and not self.settings.mcdonalds_reset_checkpoint:
            raise ValueError(
                f"McDonald's checkpoint at {checkpoint.path} exists but could not be loaded "
                f"(adapter version mismatch?). Set ADAPTER_MCDONALDS_RESET_CHECKPOINT=1 to start fresh."
            )
        stores: dict[str, dict[str, Any]] = saved.stores if saved else {}
        visited_points: set[tuple[float, float]] = saved.visited_points if saved else set()
        request_count = saved.request_count if saved else 0
        initial_feed_complete = saved.initial_feed_complete if saved else False

        stores_lock = asyncio.Lock()
        visited_lock = asyncio.Lock()
        count_lock = asyncio.Lock()
        checkpoint_lock = asyncio.Lock()
        work_queue = McDonaldsWorkQueue()
        stop_event = asyncio.Event()
        plateau_tracker = PlateauTracker()
        plateau_stop_lock = asyncio.Lock()
        plateau_stop_scheduled = False

        async def schedule_plateau_stop(*, window_new_stores: int) -> None:
            nonlocal plateau_stop_scheduled
            async with plateau_stop_lock:
                if plateau_stop_scheduled:
                    return
                plateau_stop_scheduled = True
            stop_event.set()
            abandoned = await work_queue.abort(SEARCH_CONCURRENCY)
            logger.info(
                "mcdonalds_grid_plateau",
                extra={
                    "store_count": len(stores),
                    "search_requests": request_count,
                    "window_new_stores": window_new_stores,
                    "abandoned_queue_cells": abandoned,
                },
            )

        if saved and saved.queue:
            await work_queue.put_many(saved.queue)
            logger.info(
                "mcdonalds_checkpoint_resumed",
                extra={
                    "request_count": request_count,
                    "visited_points": len(visited_points),
                    "queue_size": len(saved.queue),
                    "store_count": len(stores),
                    "initial_feed_complete": initial_feed_complete,
                },
            )
        elif saved and initial_feed_complete:
            logger.info(
                "mcdonalds_checkpoint_resumed",
                extra={
                    "request_count": request_count,
                    "visited_points": len(visited_points),
                    "queue_size": 0,
                    "store_count": len(stores),
                    "initial_feed_complete": True,
                },
            )

        logger.info(
            "mcdonalds_grid_start",
            extra={
                "initial_step_degrees": INITIAL_GRID_STEP_DEGREES,
                "min_step_degrees": MIN_GRID_STEP_DEGREES,
                "concurrency": SEARCH_CONCURRENCY,
                "checkpoint_path": str(checkpoint.path),
                "resumed": saved is not None,
            },
        )

        async def persist_checkpoint() -> None:
            async with checkpoint_lock:
                async with stores_lock, visited_lock:
                    snapshot = {
                        "request_count": request_count,
                        "initial_feed_complete": initial_feed_complete,
                        "visited_points": set(visited_points),
                        "stores": dict(stores),
                    }
                queue_snapshot = await work_queue.snapshot()
                await asyncio.to_thread(
                    checkpoint.save,
                    request_count=snapshot["request_count"],
                    initial_feed_complete=snapshot["initial_feed_complete"],
                    visited_points=snapshot["visited_points"],
                    queue=queue_snapshot,
                    stores=snapshot["stores"],
                )
                checkpoint.reopen()

        async def wait_for_plateau_shutdown(workers: list[asyncio.Task[None]]) -> None:
            try:
                await asyncio.wait_for(
                    work_queue.join(),
                    timeout=WORKER_SHUTDOWN_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "mcdonalds_queue_join_timeout",
                    extra={
                        "timeout_seconds": WORKER_SHUTDOWN_TIMEOUT_SECONDS,
                        "search_requests": request_count,
                        "store_count": len(stores),
                    },
                )
                for task in workers:
                    task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        async def finish_workers(workers: list[asyncio.Task[None]]) -> None:
            for _ in workers:
                await work_queue.put_sentinel()
            await work_queue.join()
            await asyncio.gather(*workers, return_exceptions=True)

        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers=headers,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=SEARCH_CONCURRENCY + 2,
                max_keepalive_connections=SEARCH_CONCURRENCY,
            ),
        ) as client:

            async def feed_initial_cells() -> int:
                nonlocal initial_feed_complete
                if initial_feed_complete:
                    return 0
                count = 0
                for cell in iter_initial_grid():
                    await work_queue.put(cell)
                    count += 1
                initial_feed_complete = True
                logger.info("mcdonalds_grid_feed_complete", extra={"initial_cells": count})
                await persist_checkpoint()
                return count

            async def process_cell(latitude: float, longitude: float, step: float) -> None:
                nonlocal request_count
                if stop_event.is_set():
                    return
                point_key = visited_key(latitude, longitude)
                async with visited_lock:
                    if point_key in visited_points:
                        return

                rows = await self._search_by_point(client, latitude, longitude)

                async with visited_lock:
                    visited_points.add(point_key)

                async with count_lock:
                    request_count += 1
                    current_requests = request_count

                async with stores_lock:
                    store_count_before = len(stores)
                    for row in rows:
                        parsed = parse_store_record(row)
                        if parsed is None:
                            continue
                        stores[parsed["external_id"]] = parsed
                    current_store_count = len(stores)
                    new_stores_added = current_store_count - store_count_before

                async with count_lock:
                    plateau_reached, window_new_stores = plateau_tracker.record_request(
                        new_stores_added,
                        current_store_count,
                        len(work_queue),
                    )

                if plateau_reached:
                    await schedule_plateau_stop(window_new_stores=window_new_stores)
                    return

                if stop_event.is_set():
                    return

                if should_subdivide(rows, step):
                    await work_queue.put_many(subdivide_cell(latitude, longitude, step))

                if current_requests % 1000 == 0:
                    logger.info(
                        "mcdonalds_grid_progress",
                        extra={
                            "search_requests": current_requests,
                            "queue_size": len(work_queue),
                            "store_count": current_store_count,
                            "visited_points": len(visited_points),
                            "window_new_stores": plateau_tracker.window_new_stores,
                            "window_requests": plateau_tracker.window_requests,
                        },
                    )

                interval = checkpoint_interval_for(len(work_queue))
                if current_requests % interval == 0:
                    await persist_checkpoint()

                if current_requests >= DAILY_REQUEST_BUDGET:
                    raise McDonaldsDailyQuotaExceeded(
                        f"Stopping at {DAILY_REQUEST_BUDGET} requests to stay under McDonald's daily quota; "
                        "resume after midnight China time"
                    )

            async def worker() -> None:
                while True:
                    item = await work_queue.get()
                    try:
                        if item is None:
                            return
                        await process_cell(*item)
                    finally:
                        await work_queue.task_done()

            async def heartbeat() -> None:
                last_count = -1
                last_change = time.monotonic()
                while not stop_event.is_set():
                    await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                    current = request_count
                    queue_size = len(work_queue)
                    logger.info(
                        "mcdonalds_grid_heartbeat",
                        extra={
                            "search_requests": current,
                            "queue_size": queue_size,
                            "store_count": len(stores),
                            "window_new_stores": plateau_tracker.window_new_stores,
                            "window_requests": plateau_tracker.window_requests,
                        },
                    )
                    if current != last_count:
                        last_count = current
                        last_change = time.monotonic()
                        continue
                    if time.monotonic() - last_change < STALL_RECOVERY_SECONDS:
                        continue
                    logger.warning(
                        "mcdonalds_grid_stall_recovery",
                        extra={
                            "search_requests": current,
                            "queue_size": queue_size,
                            "store_count": len(stores),
                            "stall_seconds": STALL_RECOVERY_SECONDS,
                        },
                    )
                    await persist_checkpoint()
                    for task in workers:
                        task.cancel()
                    await asyncio.gather(*workers, return_exceptions=True)
                    workers.clear()
                    for _ in range(SEARCH_CONCURRENCY):
                        workers.append(asyncio.create_task(worker()))
                    last_change = time.monotonic()
                    last_count = current

            feeder = asyncio.create_task(feed_initial_cells())
            workers = [asyncio.create_task(worker()) for _ in range(SEARCH_CONCURRENCY)]
            heartbeat_task = asyncio.create_task(heartbeat())
            crawl_completed = False
            try:
                await feeder
                if stop_event.is_set():
                    await wait_for_plateau_shutdown(workers)
                    await persist_checkpoint()
                else:
                    await work_queue.join()
                    if not stop_event.is_set():
                        await finish_workers(workers)
                        crawl_completed = True
            except McDonaldsDailyQuotaExceeded as exc:
                await persist_checkpoint()
                for task in workers:
                    task.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
                logger.error(
                    "mcdonalds_daily_quota_exceeded",
                    extra={
                        "message": str(exc),
                        "search_requests": request_count,
                        "store_count": len(stores),
                        "visited_points": len(visited_points),
                    },
                )
                raise
            except Exception:
                await persist_checkpoint()
                for task in workers:
                    task.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
                raise
            finally:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)

        if crawl_completed:
            checkpoint.clear()
        logger.info(
            "mcdonalds_fetch_complete",
            extra={
                "store_count": len(stores),
                "search_requests": request_count,
                "grid_points": len(visited_points),
            },
        )
        return list(stores.values())

    async def _search_by_point(
        self, client: httpx.AsyncClient, latitude: float, longitude: float
    ) -> list[dict[str, Any]]:
        last_exc: Exception | None = None
        for attempt in range(HTTP_MAX_ATTEMPTS):
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
                if attempt + 1 < HTTP_MAX_ATTEMPTS:
                    await asyncio.sleep(0.5 * (attempt + 1))
        if last_exc is not None:
            logger.warning(
                "mcdonalds_search_by_point_failed",
                extra={
                    "latitude": latitude,
                    "longitude": longitude,
                    "error": type(last_exc).__name__,
                },
            )
        return []

    async def parse_locations(self, raw_data: Any) -> list[RawLocation]:
        if not isinstance(raw_data, list):
            logger.warning("mcdonalds_unexpected_payload_shape", extra={"type": type(raw_data).__name__})
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
        coordinate_system = CoordinateSystem(payload.get("coordinate_system", CoordinateSystem.GCJ02.value))

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
            source_type="mcdonalds_search_by_point",
            source_url=self.search_url,
            raw_payload=payload.get("raw", payload),
        )
