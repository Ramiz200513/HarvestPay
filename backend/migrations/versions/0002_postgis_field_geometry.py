"""PostGIS: геометрия поля, рамка (bbox) и пересечения в заявке.

Что делает:
  1. В PostgreSQL включает расширение postgis.
  2. fields: + geom (PostGIS POLYGON, SRID 4326 = обычные широта/долгота) и рамка min/max lon/lat.
  3. Заполняет новые колонки для уже существующих полей из старой колонки geometry (GeoJSON).
  4. Строит GIST-индекс по geom — без него поиск пересечений перебирал бы все поля подряд.
  5. applications: + overlaps — пересечения с чужими полями на момент подачи заявки.

Revision ID: 0002
Revises: 0001
"""

import json

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _ring(geojson) -> list:
    if isinstance(geojson, str):  # SQLite может вернуть JSON строкой
        geojson = json.loads(geojson)
    return geojson["coordinates"][0]


def _ewkt(ring: list) -> str:
    return "SRID=4326;POLYGON((" + ", ".join(f"{lon} {lat}" for lon, lat in ring) + "))"


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    geom_type = sa.Text().with_variant(Geometry("POLYGON", srid=4326, spatial_index=False), "postgresql")
    with op.batch_alter_table("fields") as batch:
        batch.add_column(sa.Column("geom", geom_type, nullable=True))
        for name in ("min_lon", "min_lat", "max_lon", "max_lat"):
            batch.add_column(sa.Column(name, sa.Float(), nullable=True))

    with op.batch_alter_table("applications") as batch:
        batch.add_column(
            sa.Column(
                "overlaps",
                sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
                nullable=False,
                server_default="[]",
            )
        )

    # --- заполняем новые колонки у полей, созданных до этой миграции ---
    rows = bind.execute(sa.text("SELECT id, geometry FROM fields")).fetchall()
    set_geom = "ST_GeomFromEWKT(:ewkt)" if is_pg else ":ewkt"
    update = sa.text(
        f"UPDATE fields SET geom = {set_geom}, min_lon = :a, min_lat = :b, max_lon = :c, max_lat = :d WHERE id = :id"
    )
    for field_id, geometry in rows:
        ring = _ring(geometry)
        lons, lats = [p[0] for p in ring], [p[1] for p in ring]
        bind.execute(
            update,
            {"ewkt": _ewkt(ring), "a": min(lons), "b": min(lats), "c": max(lons), "d": max(lats), "id": field_id},
        )

    if is_pg:
        op.create_index("ix_fields_geom", "fields", ["geom"], postgresql_using="gist")
    else:
        # в SQLite ищем кандидатов по рамке — индекс по ней ускоряет отбор
        op.create_index("ix_fields_bbox", "fields", ["min_lon", "max_lon", "min_lat", "max_lat"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index("ix_fields_geom", table_name="fields")
    else:
        op.drop_index("ix_fields_bbox", table_name="fields")
    with op.batch_alter_table("applications") as batch:
        batch.drop_column("overlaps")
    with op.batch_alter_table("fields") as batch:
        for name in ("geom", "min_lon", "min_lat", "max_lon", "max_lat"):
            batch.drop_column(name)
