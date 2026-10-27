"""Маркетплейс: поставщики со скидкой, сделки, проверка юрлица, климат сезона, кадастр.

Что делает:
  1. suppliers — новая таблица; products.supplier (текст) заменяется ссылкой supplier_id.
     Поставщики уже существующих товаров переносятся автоматически, скидка — по таблице ниже или 6 %.
  2. deals — сделка по одобренной заявке: сколько платим поставщику, сколько вернёт фермер, журнал.
  3. farms: + compliance (налоги, аресты, суды, субсидии) и checks (чек-лист проверки).
  4. fields: + cadastral_number.  field_seasons: + frost_days, heat_days.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

DEFAULT_DISCOUNT = 0.06
KNOWN_DISCOUNTS = {  # демо-поставщики из seed.py
    "Агрохолдинг Север (демо)": 0.06,
    "СемКорм (демо)": 0.07,
    "АгроХим КЗ (демо)": 0.05,
    "ЗащитаПолей (демо)": 0.07,
}


def json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()

    suppliers = op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("discount", sa.Float(), nullable=False),
    )

    # --- поставщики уже существующих товаров ---
    names = [row[0] for row in bind.execute(sa.text("SELECT DISTINCT supplier FROM products")).fetchall()]
    if names:
        op.bulk_insert(suppliers, [{"name": n, "discount": KNOWN_DISCOUNTS.get(n, DEFAULT_DISCOUNT)} for n in names])

    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("supplier_id", sa.Integer(), nullable=True))
    bind.execute(
        sa.text("UPDATE products SET supplier_id = (SELECT s.id FROM suppliers s WHERE s.name = products.supplier)")
    )
    with op.batch_alter_table("products") as batch:
        batch.alter_column("supplier_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_products_supplier_id", "suppliers", ["supplier_id"], ["id"])
        batch.create_index("ix_products_supplier_id", ["supplier_id"])
        batch.drop_column("supplier")

    with op.batch_alter_table("farms") as batch:
        batch.add_column(sa.Column("compliance", json_type(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("checks", json_type(), nullable=False, server_default="[]"))

    with op.batch_alter_table("fields") as batch:
        batch.add_column(sa.Column("cadastral_number", sa.String(32), nullable=True))

    with op.batch_alter_table("field_seasons") as batch:
        batch.add_column(sa.Column("frost_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("heat_days", sa.Integer(), nullable=True))

    op.create_table(
        "deals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("score_class", sa.String(1), nullable=False),
        sa.Column("goods_amount", sa.Integer(), nullable=False),
        sa.Column("discount_rate", sa.Float(), nullable=False),
        sa.Column("supplier_payout", sa.Integer(), nullable=False),
        sa.Column("fee_rate", sa.Float(), nullable=False),
        sa.Column("farmer_total", sa.Integer(), nullable=False),
        sa.Column("funding_rate", sa.Float(), nullable=False),
        sa.Column("payout_date", sa.Date(), nullable=False),
        sa.Column("schedule", json_type(), nullable=False),
        sa.Column("paid_amount", sa.Integer(), nullable=False),
        sa.Column("events", json_type(), nullable=False),
        sa.Column("monitoring", json_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_deals_status", "deals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_deals_status", table_name="deals")
    op.drop_table("deals")
    with op.batch_alter_table("field_seasons") as batch:
        batch.drop_column("heat_days")
        batch.drop_column("frost_days")
    with op.batch_alter_table("fields") as batch:
        batch.drop_column("cadastral_number")
    with op.batch_alter_table("farms") as batch:
        batch.drop_column("checks")
        batch.drop_column("compliance")

    bind = op.get_bind()
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("supplier", sa.String(255), nullable=True))
    bind.execute(
        sa.text("UPDATE products SET supplier = (SELECT s.name FROM suppliers s WHERE s.id = products.supplier_id)")
    )
    with op.batch_alter_table("products") as batch:
        batch.alter_column("supplier", existing_type=sa.String(255), nullable=False)
        batch.drop_index("ix_products_supplier_id")
        batch.drop_constraint("fk_products_supplier_id", type_="foreignkey")
        batch.drop_column("supplier_id")
    op.drop_table("suppliers")
