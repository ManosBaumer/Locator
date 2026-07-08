from datetime import datetime
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CoordinateSystem


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("chain_id", "external_id", name="uq_locations_chain_external"),
        Index("ix_locations_geom", "geom", postgresql_using="gist"),
        Index("ix_locations_name_address", "name", "address"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(180), nullable=False)
    name: Mapped[str | None] = mapped_column(String(240))
    address: Mapped[str | None] = mapped_column(Text)
    province: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    district: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7))
    coordinate_system: Mapped[CoordinateSystem] = mapped_column(
        Enum(CoordinateSystem, name="coordinate_system"),
        nullable=False,
        default=CoordinateSystem.GCJ02,
    )
    geom = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    chain = relationship("Chain", back_populates="locations")
