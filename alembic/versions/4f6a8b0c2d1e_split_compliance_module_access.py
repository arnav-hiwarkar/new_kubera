"""split compliance module access

Revision ID: 4f6a8b0c2d1e
Revises: e2c4a6b8d0f1
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4f6a8b0c2d1e"
down_revision: Union[str, None] = "e2c4a6b8d0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve existing entries, append the two canonical grants, and de-duplicate
    # them if a row already contains canonical values.
    op.execute(
        """
        UPDATE company_users AS cu
        SET accessible_modules = (
            SELECT COALESCE(jsonb_agg(module ORDER BY first_position), '[]'::jsonb) AS modules
            FROM (
                SELECT module, MIN(position) AS first_position
                FROM jsonb_array_elements_text(
                    (cu.accessible_modules - 'compliance')
                    || '["roc", "secretarial"]'::jsonb
                ) WITH ORDINALITY AS expanded(module, position)
                GROUP BY module
            ) AS deduplicated
        )
        WHERE cu.accessible_modules ? 'compliance'
        """
    )


def downgrade() -> None:
    # Granular assignments necessarily collapse back to the combined grant.
    op.execute(
        """
        UPDATE company_users AS cu
        SET accessible_modules = (
            SELECT COALESCE(jsonb_agg(module ORDER BY first_position), '[]'::jsonb) AS modules
            FROM (
                SELECT module, MIN(position) AS first_position
                FROM jsonb_array_elements_text(
                    (cu.accessible_modules - 'roc' - 'secretarial')
                    || '["compliance"]'::jsonb
                ) WITH ORDINALITY AS collapsed(module, position)
                GROUP BY module
            ) AS deduplicated
        )
        WHERE cu.accessible_modules ?| ARRAY['roc', 'secretarial']
        """
    )
