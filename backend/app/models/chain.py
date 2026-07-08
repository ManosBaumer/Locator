from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Chain(Base):
    __tablename__ = "chains"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="CN")
    website: Mapped[str | None] = mapped_column(Text)
    store_locator_url: Mapped[str | None] = mapped_column(Text)

    category = relationship("Category", back_populates="chains")
    locations = relationship("Location", back_populates="chain")
    ingestion_runs = relationship("IngestionRun", back_populates="chain")
