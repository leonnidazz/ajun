"""Phase 1a Core Tables and System Configurations Seed

Revision ID: 001_phase1a_core
Revises: 
Create Date: 2026-10-31 05:45:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_phase1a_core"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SYSTEM_CONFIG_SEEDS = [
    ("ALLOWED_CAMPUS_DOMAINS", "ui.ac.id,ugm.ac.id,itb.ac.id", "Daftar domain email kampus yang diizinkan"),
    ("INITIAL_BONUS_COINS", "30", "Bonus koin pendaftaran pengguna baru terverifikasi kampus"),
    ("MAX_TOPUP_PER_TX_IDR", "100000", "Batas maksimal nominal top-up per transaksi dalam Rupiah"),
    ("MAX_USER_BALANCE_COINS", "200", "Batas maksimal saldo koin pengguna"),
    ("MATCH_OVERLAP_MINUTES", "90", "Jendela proteksi bentrok waktu perjalanan aktif"),
    ("REOPEN_MIN_LEAD_MINUTES", "30", "Batas minimal waktu menuju keberangkatan untuk membuka kembali rute"),
    ("REQUEST_RESPONSE_MINUTES", "30", "Batas waktu tunggu respons ajakan tumpangan"),
    ("CONFIRMATION_WINDOW_MINUTES", "60", "Jendela waktu konfirmasi pasca tawaran diterima"),
    ("MIN_CONFIRMATION_LEAD_MINUTES", "15", "Garansi batas waktu minimal konfirmasi sebelum berangkat"),
    ("MIN_REQUEST_LEAD_MINUTES", "45", "Batas minimal lead time pemesanan awal sebelum berangkat"),
]


def upgrade() -> None:
    # 1. users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("google_sub", sa.String(255), unique=True, nullable=True),
        sa.Column("email", sa.String(255), unique=True, nullable=True),
        sa.Column("phone_number", sa.String(50), unique=True, nullable=True),
        sa.Column("campus_email", sa.String(255), unique=True, nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("campus_name", sa.String(255), nullable=True),
        sa.Column("is_identity_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("campus_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("campus_verification_method", sa.String(50), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_google_sub", "users", ["google_sub"])
    op.create_index("ix_users_email", "users", ["email"])

    # 2. refresh_tokens table
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # 3. system_configurations table
    op.create_table(
        "system_configurations",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Idempotent Seed Data Migration
    conn = op.get_bind()
    for key, val, desc in SYSTEM_CONFIG_SEEDS:
        conn.execute(
            sa.text(
                "INSERT INTO system_configurations (key, value, description, updated_at) "
                "VALUES (:k, :v, :d, now()) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"k": key, "v": val, "d": desc},
        )


def downgrade() -> None:
    op.drop_table("system_configurations")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
