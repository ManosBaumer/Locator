import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import GeocodingCache
from app.models.enums import CoordinateSystem
from app.utils.coordinates import gcj02_to_wgs84
from app.utils.geocoding.base import GeocodeResult, Geocoder

logger = logging.getLogger(__name__)

AMAP_PLACE_TEXT = "https://restapi.amap.com/v3/place/text"
MIN_ACCEPTABLE_GEOCODE_CONFIDENCE = 0.7


def normalize_address(address: str) -> str:
    return " ".join(address.strip().split())


class AmapGeocoder(Geocoder):
    provider = "amap"
    endpoint = "https://restapi.amap.com/v3/geocode/geo"

    def __init__(self, settings: Settings, session: AsyncSession):
        self.settings = settings
        self.session = session

    async def geocode(self, address: str, city: str | None = None) -> GeocodeResult | None:
        normalized = normalize_address(address)
        cached = await self.session.scalar(
            select(GeocodingCache).where(
                GeocodingCache.normalized_address == normalized,
                GeocodingCache.provider == self.provider,
            )
        )
        if cached is not None:
            return GeocodeResult(
                raw_address=cached.raw_address,
                normalized_address=cached.normalized_address,
                latitude=float(cached.latitude),
                longitude=float(cached.longitude),
                coordinate_system=CoordinateSystem.WGS84,
                confidence=float(cached.confidence) if cached.confidence is not None else None,
            )

        if not self.settings.amap_api_key:
            logger.warning("amap_api_key_missing", extra={"address": normalized})
            return None

        params = {"key": self.settings.amap_api_key, "address": normalized}
        if city:
            params["city"] = city

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
            payload = response.json()

        geocodes = payload.get("geocodes") or []
        if payload.get("status") != "1" or not geocodes:
            logger.info("amap_geocode_empty", extra={"address": normalized, "payload": payload})
            return None

        first = geocodes[0]
        location = first.get("location")
        if not location or "," not in location:
            return None

        gcj_lng, gcj_lat = [float(part) for part in location.split(",", 1)]
        wgs_lng, wgs_lat = gcj02_to_wgs84(gcj_lng, gcj_lat)
        confidence = _confidence_from_level(first.get("level"))
        if confidence is not None and confidence < MIN_ACCEPTABLE_GEOCODE_CONFIDENCE:
            logger.info(
                "amap_geocode_low_confidence",
                extra={
                    "address": normalized,
                    "city": city,
                    "level": first.get("level"),
                    "confidence": confidence,
                },
            )
            return None

        self.session.add(
            GeocodingCache(
                raw_address=address,
                normalized_address=normalized,
                latitude=wgs_lat,
                longitude=wgs_lng,
                provider=self.provider,
                confidence=confidence,
            )
        )
        await self.session.flush()

        return GeocodeResult(
            raw_address=address,
            normalized_address=normalized,
            latitude=wgs_lat,
            longitude=wgs_lng,
            coordinate_system=CoordinateSystem.WGS84,
            confidence=confidence,
            formatted_address=first.get("formatted_address"),
            province=first.get("province"),
            city=first.get("city"),
            district=first.get("district"),
        )

    async def search_poi(self, keywords: str, city: str | None = None) -> GeocodeResult | None:
        normalized = normalize_address(keywords)
        if not self.settings.amap_api_key:
            logger.warning("amap_api_key_missing", extra={"keywords": normalized})
            return None

        params: dict[str, str] = {
            "key": self.settings.amap_api_key,
            "keywords": normalized,
            "citylimit": "true",
        }
        if city:
            params["city"] = city

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(AMAP_PLACE_TEXT, params=params)
            response.raise_for_status()
            payload = response.json()

        pois = payload.get("pois") or []
        if payload.get("status") != "1" or not pois:
            logger.info("amap_poi_search_empty", extra={"keywords": normalized, "city": city})
            return None

        first = pois[0]
        location = first.get("location")
        if not location or "," not in location:
            return None

        gcj_lng, gcj_lat = [float(part) for part in location.split(",", 1)]
        wgs_lng, wgs_lat = gcj02_to_wgs84(gcj_lng, gcj_lat)
        formatted_address = first.get("address") or None
        if formatted_address and first.get("adname"):
            formatted_address = f"{first['adname']}{formatted_address}"

        return GeocodeResult(
            raw_address=keywords,
            normalized_address=normalized,
            latitude=wgs_lat,
            longitude=wgs_lng,
            coordinate_system=CoordinateSystem.WGS84,
            confidence=0.9,
            formatted_address=formatted_address,
            province=first.get("pname"),
            city=first.get("cityname"),
            district=first.get("adname"),
        )


def _confidence_from_level(level: str | None) -> float | None:
    if not level:
        return None
    high = {"门牌号", "兴趣点", "道路"}
    medium = {"道路交叉路口", "村庄", "热点商圈"}
    if level in high:
        return 0.9
    if level in medium:
        return 0.7
    return 0.5
