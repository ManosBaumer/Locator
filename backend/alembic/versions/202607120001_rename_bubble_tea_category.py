"""rename bubble-tea category to tea-shop

Revision ID: 202607120001
Revises: 202606110001
Create Date: 2026-07-12 00:01:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "202607120001"
down_revision: Union[str, None] = "202606110001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE categories
        SET name = 'Tea Shop', slug = 'tea-shop'
        WHERE slug = 'bubble-tea'
        """
    )
    op.execute(
        """
        INSERT INTO categories (name, slug)
        SELECT 'Tea Shop', 'tea-shop'
        WHERE NOT EXISTS (SELECT 1 FROM categories WHERE slug = 'tea-shop')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE categories
        SET name = 'Bubble Tea', slug = 'bubble-tea'
        WHERE slug = 'tea-shop'
        """
    )
