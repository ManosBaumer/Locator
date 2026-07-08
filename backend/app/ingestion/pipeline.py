import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.ingestion.adapters.base import BaseChainAdapter
from app.ingestion.adapters.mcdonalds import McDonaldsDailyQuotaExceeded
from app.models import Chain, IngestionFailure, IngestionRun
from app.models.enums import CoordinateSystem, IngestionRunStatus
from app.schemas.poi import NormalizedLocation, RawLocation
from app.services.location_dedup import resolve_canonical_external_id
from app.services.location_upsert import upsert_location
from app.ingestion.amap_regions import (
    is_excluded_mainland_coordinates,
    is_excluded_mainland_text,
)
from app.ingestion.geocode_hints import geocode_city_candidates, join_region
from app.utils.coordinates import to_wgs84
from app.utils.geocoding.amap import AmapGeocoder

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self, session: AsyncSession, adapter: BaseChainAdapter):
        self.session = session
        self.adapter = adapter
        self.settings = get_settings()
        self._spatial_dedup_cache: dict[tuple[int, str, int, int], str] = {}

    async def run(self) -> IngestionRun:
        chain = await self._get_chain()
        run = IngestionRun(
            chain_id=chain.id,
            status=IngestionRunStatus.RUNNING,
            adapter_version=self.adapter.adapter_version,
            source_url=self.adapter.source_url,
        )
        self.session.add(run)
        await self.session.flush()

        try:
            logger.info("ingestion_fetch_start", extra={"chain": self.adapter.chain_slug})
            raw_data = await self.adapter.fetch_raw_data()
            return await self._upsert_raw_data(run, raw_data)
        except McDonaldsDailyQuotaExceeded as exc:
            logger.warning(
                "mcdonalds_quota_upserting_checkpoint",
                extra={"chain": self.adapter.chain_slug, "message": str(exc)},
            )
            raw_data = self.adapter.load_checkpoint_stores()
            run = await self._upsert_raw_data(run, raw_data)
            run.status = IngestionRunStatus.PARTIAL
            run.error_summary = f"Daily McDonald's API quota exceeded; upserted checkpoint ({run.upserted_count} stores)"
            run.finished_at = datetime.now(timezone.utc)
            await self.session.commit()
            return run
        except Exception as exc:
            run.status = IngestionRunStatus.FAILED
            run.error_summary = str(exc)
            run.finished_at = datetime.now(timezone.utc)
            await self.session.commit()
            logger.exception("ingestion_failed", extra={"chain": self.adapter.chain_slug})
            return run

    async def upsert_raw_data(self, raw_data: list) -> IngestionRun:
        chain = await self._get_chain()
        run = IngestionRun(
            chain_id=chain.id,
            status=IngestionRunStatus.RUNNING,
            adapter_version=self.adapter.adapter_version,
            source_url=self.adapter.source_url,
        )
        self.session.add(run)
        await self.session.flush()
        try:
            return await self._upsert_raw_data(run, raw_data)
        except Exception as exc:
            run.status = IngestionRunStatus.FAILED
            run.error_summary = str(exc)
            run.finished_at = datetime.now(timezone.utc)
            await self.session.commit()
            logger.exception("ingestion_failed", extra={"chain": self.adapter.chain_slug})
            return run

    async def _upsert_raw_data(self, run: IngestionRun, raw_data: list) -> IngestionRun:
        raw_locations = await self.adapter.parse_locations(raw_data)
        run.fetched_count = len(raw_locations)
        run.parsed_count = len(raw_locations)

        seen_at = datetime.now(timezone.utc)
        geocoder = AmapGeocoder(self.settings, self.session)
        for raw in raw_locations:
            try:
                normalized = await self.adapter.normalize(raw)
                enriched = await self._enrich(normalized, geocoder)
                self._validate(enriched)
                wgs_lng, wgs_lat = self._wgs84(enriched)
                external_id = await resolve_canonical_external_id(
                    self.session,
                    chain_id=run.chain_id,
                    external_id=enriched.external_id,
                    name=enriched.name,
                    wgs_latitude=wgs_lat,
                    wgs_longitude=wgs_lng,
                    run_cache=self._spatial_dedup_cache,
                )
                await upsert_location(
                    self.session,
                    chain_id=run.chain_id,
                    external_id=external_id,
                    name=enriched.name,
                    address=enriched.address,
                    province=enriched.province,
                    city=enriched.city,
                    district=enriched.district,
                    postal_code=enriched.postal_code,
                    latitude=enriched.latitude,
                    longitude=enriched.longitude,
                    coordinate_system=enriched.coordinate_system,
                    wgs84_latitude=wgs_lat,
                    wgs84_longitude=wgs_lng,
                    source_type=enriched.source_type,
                    source_url=enriched.source_url,
                    raw_payload=enriched.raw_payload,
                    seen_at=seen_at,
                )
                run.upserted_count += 1
            except Exception as exc:
                run.failed_count += 1
                self.session.add(
                    IngestionFailure(
                        run_id=run.id,
                        external_id=_external_id(raw),
                        stage="record",
                        reason=str(exc),
                        raw_payload=raw.payload,
                    )
                )

        run.status = (
            IngestionRunStatus.SUCCESS
            if run.failed_count == 0
            else IngestionRunStatus.PARTIAL
        )
        run.finished_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info(
            "ingestion_complete",
            extra={
                "chain": self.adapter.chain_slug,
                "upserted": run.upserted_count,
                "failed": run.failed_count,
            },
        )
        return run

    async def _get_chain(self) -> Chain:
        chain = await self.session.scalar(select(Chain).where(Chain.slug == self.adapter.chain_slug))
        if chain is None:
            raise ValueError(f"Chain is not seeded: {self.adapter.chain_slug}")
        return chain

    async def _enrich(
        self, location: NormalizedLocation, geocoder: AmapGeocoder
    ) -> NormalizedLocation:
        if location.latitude is not None and location.longitude is not None:
            return location
        if not location.address:
            return location
        result = await self._geocode_location(location, geocoder)
        if result is None:
            return location
        updates: dict[str, object] = {
            "latitude": result.latitude,
            "longitude": result.longitude,
            "coordinate_system": CoordinateSystem.WGS84,
        }
        if _text_has_encoding_corruption(location.address) or _text_has_encoding_corruption(
            location.name
        ):
            if result.formatted_address and not _text_has_encoding_corruption(
                result.formatted_address
            ):
                updates["address"] = result.formatted_address
        return location.model_copy(update=updates)

    async def _geocode_location(
        self, location: NormalizedLocation, geocoder: AmapGeocoder
    ):
        addresses: list[str] = []
        seen_addresses: set[str] = set()
        for candidate in (
            location.address,
            *_geocode_fallback_addresses(location.address or ""),
            join_region(location.province, location.city, location.district),
        ):
            if not candidate or candidate in seen_addresses:
                continue
            seen_addresses.add(candidate)
            addresses.append(candidate)

        for address in addresses:
            for city in geocode_city_candidates(location):
                result = await geocoder.geocode(address, city=city)
                if result is not None:
                    return result

        if location.name:
            for city in geocode_city_candidates(location):
                result = await geocoder.search_poi(location.name, city=city)
                if result is not None:
                    return result

        for city in geocode_city_candidates(location):
            if not city:
                continue
            result = await geocoder.geocode(city, city=city)
            if result is not None:
                return result
        return None

    def _validate(self, location: NormalizedLocation) -> None:
        if not location.external_id:
            raise ValueError("external_id is required")
        if not location.address and not location.name:
            raise ValueError("name or address is required")
        if location.latitude is None or location.longitude is None:
            raise ValueError("coordinates are required after enrichment")
        for field in (location.province, location.city, location.district, location.address, location.name):
            if is_excluded_mainland_text(field):
                raise ValueError("location is outside mainland China scope")
        if is_excluded_mainland_coordinates(location.longitude, location.latitude):
            raise ValueError("coordinates are outside mainland China scope")
        if not (73 <= location.longitude <= 136 and 3 <= location.latitude <= 54):
            raise ValueError("coordinates are outside expected China bounds")

    def _wgs84(self, location: NormalizedLocation) -> tuple[float, float]:
        if location.latitude is None or location.longitude is None:
            raise ValueError("coordinates are required")
        return to_wgs84(location.longitude, location.latitude, location.coordinate_system)


def _text_has_encoding_corruption(value: str | None) -> bool:
    return bool(value and ("?" in value or "\ufffd" in value))


def _geocode_fallback_addresses(address: str) -> list[str]:
    candidates: list[str] = []
    shortened = re.sub(r"[、，／/].*", "", address).strip()
    if shortened and shortened != address:
        candidates.append(shortened)

    for pattern in (r"^(.+?广场)", r"^(.+?(?:购物中心|购物广场))"):
        match = re.match(pattern, address)
        if match:
            candidates.append(match.group(1))

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen and candidate != address:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _external_id(raw: RawLocation) -> str | None:
    for key in ("external_id", "orgResourceCode", "id", "storeId", "store_id", "poiId"):
        value = raw.payload.get(key)
        if value:
            return str(value)
    return None
