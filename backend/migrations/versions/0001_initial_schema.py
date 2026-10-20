"""Начальная схема — ровно то, что было в версии 0.1 (7 таблиц из ER-диаграммы).

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def json_type():
    # JSONB в PostgreSQL, обычный JSON в SQLite — так же, как в models.py
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "farms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bin", sa.String(12), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("legal_form", sa.String(255)),
        sa.Column("registered_at", sa.Date()),
        sa.Column("verification_status", sa.String(20), nullable=False),
        sa.Column("verification_reasons", json_type(), nullable=False),
        sa.Column("registry_source", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_farms_bin", "farms", ["bin"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("supplier", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
    )

    op.create_table(
        "fields",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("farm_id", sa.Integer(), sa.ForeignKey("farms.id"), nullable=False),
        sa.Column("geometry", json_type(), nullable=False),
        sa.Column("crop", sa.String(50), nullable=False),
        sa.Column("area_ha", sa.Float(), nullable=False),
        sa.Column("centroid_lat", sa.Float(), nullable=False),
        sa.Column("centroid_lon", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fields_farm_id", "fields", ["farm_id"])

    op.create_table(
        "applications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("farm_id", sa.Integer(), sa.ForeignKey("farms.id"), nullable=False),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("requested_amount", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_applications_farm_id", "applications", ["farm_id"])
    op.create_index("ix_applications_status", "applications", ["status"])

    op.create_table(
        "field_seasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("field_id", sa.Integer(), sa.ForeignKey("fields.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("ndvi_peak", sa.Float()),
        sa.Column("ndvi_mean", sa.Float()),
        sa.Column("soil_moisture", sa.Float()),
        sa.Column("scenes", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.UniqueConstraint("field_id", "year", name="uq_field_year"),
    )
    op.create_index("ix_field_seasons_field_id", "field_seasons", ["field_id"])

    op.create_table(
        "application_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
    )
    op.create_index("ix_application_items_application_id", "application_items", ["application_id"])

    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False, unique=True),
        sa.Column("score", sa.Float()),
        sa.Column("score_class", sa.String(1), nullable=False),
        sa.Column("components", json_type(), nullable=False),
        sa.Column("reasons", json_type(), nullable=False),
        sa.Column("limit_amount", sa.Integer(), nullable=False),
        sa.Column("approved_amount", sa.Integer(), nullable=False),
        sa.Column("schedule", json_type(), nullable=False),
        sa.Column("decided_by", sa.String(20), nullable=False),
        sa.Column("analyst_comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in ("decisions", "application_items", "field_seasons", "applications", "fields", "products", "farms"):
        op.drop_table(table)
