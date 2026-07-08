from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import CoordinateSystem


class RawLocation(BaseModel):
    payload: dict[str, Any]


class NormalizedLocation(BaseModel):
    external_id: str
    name: str | None = None
    address: str | None = None
    province: str | None = None
    city: str | None = None
    district: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    coordinate_system: CoordinateSystem = CoordinateSystem.GCJ02
    source_type: str
    source_url: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class LocationGeoJSONProperties(BaseModel):
    id: int
    name: str | None
    chain_slug: str
    category_slug: str
    address: str | None
    city: str | None
