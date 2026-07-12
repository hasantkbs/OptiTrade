"""Initial schema: analysis_predictions + ohlcv_data

Revision ID: 0001
Revises:
Create Date: 2026-06-30

Creates two tables:
  analysis_predictions — prediction tracking (mandatory by architecture rules)
  ohlcv_data           — OHLCV candlestick cache (TimescaleDB hypertable if available)

TimescaleDB hypertable conversion is attempted but silently skipped when the
extension is not installed, so migrations run on plain PostgreSQL too.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── analysis_predictions ─────────────────────────────────────────────────
    op.create_table(
        "analysis_predictions",
        sa.Column("id",           UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol",       sa.String(20),  nullable=False),
        sa.Column("asset_type",   sa.String(20),  nullable=False),
        sa.Column("score",        sa.Integer(),   nullable=False),
        sa.Column("decision_code", sa.String(20), nullable=False),
        sa.Column("confidence_pct", sa.Float(),   nullable=True),

        sa.Column("indicators_json",        JSONB(), nullable=True),
        sa.Column("scoring_breakdown_json", JSONB(), nullable=True),
        sa.Column("long_signals",           JSONB(), nullable=True),
        sa.Column("short_signals",          JSONB(), nullable=True),

        sa.Column(
            "predicted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("actual_price_at_prediction", sa.Float(), nullable=True),
        sa.Column("actual_price_1d",            sa.Float(), nullable=True),
        sa.Column("actual_price_7d",            sa.Float(), nullable=True),
        sa.Column("actual_price_30d",           sa.Float(), nullable=True),
        sa.Column("actual_outcome",      sa.String(20), nullable=True),
        sa.Column("prediction_accuracy", sa.Float(),    nullable=True),
    )
    op.create_index("ix_ap_symbol",       "analysis_predictions", ["symbol"])
    op.create_index("ix_ap_predicted_at", "analysis_predictions", ["predicted_at"])
    op.create_index("ix_ap_symbol_time",  "analysis_predictions", ["symbol", "predicted_at"])

    # ── ohlcv_data ────────────────────────────────────────────────────────────
    op.create_table(
        "ohlcv_data",
        sa.Column("time",   sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("open",   sa.Float(),    nullable=False),
        sa.Column("high",   sa.Float(),    nullable=False),
        sa.Column("low",    sa.Float(),    nullable=False),
        sa.Column("close",  sa.Float(),    nullable=False),
        sa.Column("volume", sa.Float(),    nullable=False),
        sa.PrimaryKeyConstraint("time", "symbol"),
    )

    # TimescaleDB hypertable — optional.  Ignored if extension is not present.
    conn = op.get_bind()
    try:
        result = conn.execute(
            sa.text(
                "SELECT EXISTS("
                "  SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'"
                ")"
            )
        )
        has_timescale = result.scalar()
        if has_timescale:
            conn.execute(
                sa.text(
                    "SELECT create_hypertable('ohlcv_data', 'time', if_not_exists => TRUE)"
                )
            )
    except Exception:
        pass  # TimescaleDB not available; plain table is fine


def downgrade() -> None:
    op.drop_table("ohlcv_data")
    op.drop_index("ix_ap_symbol_time",  table_name="analysis_predictions")
    op.drop_index("ix_ap_predicted_at", table_name="analysis_predictions")
    op.drop_index("ix_ap_symbol",       table_name="analysis_predictions")
    op.drop_table("analysis_predictions")
