"""initial schema

Revision ID: 202606110001
Revises:
Create Date: 2026-06-11 00:01:00
"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202606110001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    coordinate_system = sa.Enum("WGS84", "GCJ02", "BD09", name="coordinate_system")
    ingestion_run_status = sa.Enum(
        "RUNNING",
        "SUCCESS",
        "PARTIAL",
        "FAILED",
        name="ingestion_run_status",
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)

    op.create_table(
        "chains",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("store_locator_url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chains_slug", "chains", ["slug"], unique=True)

    op.create_table(
        "geocoding_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("raw_address", sa.Text(), nullable=False),
        sa.Column("normalized_address", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_address", "provider", name="uq_geocode_address_provider"),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("status", ingestion_run_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("parsed_count", sa.Integer(), nullable=False),
        sa.Column("upserted_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("adapter_version", sa.String(length=80), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["chain_id"], ["chains.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_runs_chain_id", "ingestion_runs", ["chain_id"])

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=180), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("province", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("district", sa.String(length=120), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=True),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("coordinate_system", coordinate_system, nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geography(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["chain_id"], ["chains.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain_id", "external_id", name="uq_locations_chain_external"),
    )
    op.create_index("ix_locations_chain_id", "locations", ["chain_id"])
    op.create_index("ix_locations_city", "locations", ["city"])
    op.create_index("ix_locations_geom", "locations", ["geom"], postgresql_using="gist")
    op.create_index("ix_locations_name_address", "locations", ["name", "address"])

    op.create_table(
        "ingestion_failures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=180), nullable=True),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ingestion_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_failures_run_id", "ingestion_failures", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_failures_run_id", table_name="ingestion_failures")
    op.drop_table("ingestion_failures")
    op.drop_index("ix_locations_name_address", table_name="locations")
    op.drop_index("ix_locations_geom", table_name="locations")
    op.drop_index("ix_locations_city", table_name="locations")
    op.drop_index("ix_locations_chain_id", table_name="locations")
    op.drop_table("locations")
    op.drop_index("ix_ingestion_runs_chain_id", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("geocoding_cache")
    op.drop_index("ix_chains_slug", table_name="chains")
    op.drop_table("chains")
    op.drop_index("ix_categories_slug", table_name="categories")
    op.drop_table("categories")
    sa.Enum(name="ingestion_run_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="coordinate_system").drop(op.get_bind(), checkfirst=True)
