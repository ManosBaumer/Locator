from dataclasses import dataclass

from app.models.enums import CoordinateSystem


@dataclass(frozen=True)
class GeocodeResult:
    raw_address: str
    normalized_address: str
    latitude: float
    longitude: float
    coordinate_system: CoordinateSystem
    confidence: float | None
    formatted_address: str | None = None
    province: str | None = None
    city: str | None = None
    district: str | None = None


class Geocoder:
    async def geocode(self, address: str, city: str | None = None) -> GeocodeResult | None:
        raise NotImplementedError
