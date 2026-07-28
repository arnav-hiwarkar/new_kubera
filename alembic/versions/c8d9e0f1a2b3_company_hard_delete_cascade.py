"""complete the FK cascade chain so a company can be hard-deleted (purged)

Revision ID: c8d9e0f1a2b3
Revises: b7c1d2e3f4a5
Create Date: 2026-07-28 00:00:00.000000

`a2b3c4d5e6f7` made every direct `company_id` FK cascade, but the grandchildren
did not, so `DELETE FROM companies` still aborted on an FK violation and the
operator "delete company" path could only archive. This finishes the chain:

- the five NOT NULL child->parent FKs that blocked the delete become CASCADE;
- the four nullable back-pointers into `documents`/`document_versions` become
  SET NULL, so they never dictate the delete order (and a *global* document type
  pointing at a company-owned template survives the purge);
- `documents.current_version_id` carried TWO constraints (the unnamed one from
  `70e5eedbe8e8` plus `fk_documents_current_version_id` added by `4709dd02ce22`
  without dropping the first) — collapsed into one.

Constraint names are looked up from `pg_constraint` instead of assumed, so this
applies cleanly to databases whose FK names drifted (e.g. built by `create_all`).

Also repairs `company_users` email uniqueness idempotently: a database built by
`Base.metadata.create_all` rather than alembic can still carry the original global
`UNIQUE (email)` constraint, which makes re-registering a freed email fail with a
raw IntegrityError (HTTP 500) instead of being allowed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, None] = 'b7c1d2e3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, referenced table, ondelete, constraint name to settle on)
#
# Every FK below points at a row the purge destroys, so leaving any of them at NO
# ACTION is not merely untidy: Postgres fires cascade and NO ACTION checks as AFTER
# triggers in constraint order, so a NO ACTION reference can be checked while the
# rows that satisfy it are still queued for deletion, and the whole DELETE aborts.
# NOT NULL columns therefore CASCADE and nullable ones SET NULL. Outside a purge
# these are unreachable: user delete is a soft delete, and the bucket / ledger-group
# / document-type / engagement delete endpoints all refuse when rows still point at
# the target (docvault.delete_bucket, auditease.delete_ledger_group,
# compliance.delete_document_type, auditease.delete_engagement).
_FKS = [
    # Blocked the delete outright: NOT NULL children of a cascaded parent.
    ("document_versions", "document_id", "documents", "CASCADE",
     "document_versions_document_id_fkey"),
    ("audit_entries", "engagement_id", "audit_engagements", "CASCADE",
     "audit_entries_engagement_id_fkey"),
    ("requirement_requests", "engagement_id", "audit_engagements", "CASCADE",
     "requirement_requests_engagement_id_fkey"),
    ("queries", "engagement_id", "audit_engagements", "CASCADE",
     "queries_engagement_id_fkey"),
    ("audit_entry_lines", "ledger_id", "trial_balance_accounts", "CASCADE",
     "audit_entry_lines_ledger_id_fkey"),
    # Nullable back-pointers: must not constrain the delete order.
    ("documents", "current_version_id", "document_versions", "SET NULL",
     "fk_documents_current_version_id"),
    ("requirement_requests", "fulfilled_document_id", "documents", "SET NULL",
     "requirement_requests_fulfilled_document_id_fkey"),
    ("query_messages", "attached_document_id", "documents", "SET NULL",
     "query_messages_attached_document_id_fkey"),
    ("document_types", "template_file_id", "documents", "SET NULL",
     "document_types_template_file_id_fkey"),
    # References to company_users: cascaded away with the company, so anything
    # pointing at them has to go (or let go) at the same time.
    ("company_users", "manager_id", "company_users", "SET NULL",
     "fk_company_users_manager_id"),
    ("buckets", "created_by", "company_users", "SET NULL",
     "buckets_created_by_fkey"),
    ("documents", "created_by", "company_users", "SET NULL",
     "documents_created_by_fkey"),
    ("document_versions", "uploaded_by", "company_users", "SET NULL",
     "document_versions_uploaded_by_fkey"),
    ("assets", "custodian_id", "company_users", "SET NULL",
     "assets_custodian_id_fkey"),
    ("kra_items", "manager_id", "company_users", "SET NULL",
     "kra_items_manager_id_fkey"),
    ("audit_engagements", "created_by", "company_users", "CASCADE",
     "audit_engagements_created_by_fkey"),
    ("sales_records", "user_id", "company_users", "CASCADE",
     "sales_records_user_id_fkey"),
    ("kra_items", "user_id", "company_users", "CASCADE",
     "kra_items_user_id_fkey"),
    # References to other cascaded tenant rows.
    ("documents", "bucket_id", "buckets", "SET NULL",
     "documents_bucket_id_fkey"),
    ("assets", "document_id", "documents", "SET NULL",
     "assets_document_id_fkey"),
    ("meeting_records", "document_id", "documents", "SET NULL",
     "meeting_records_document_id_fkey"),
    ("meeting_records", "doc_type_id", "document_types", "CASCADE",
     "meeting_records_doc_type_id_fkey"),
    ("trial_balance_accounts", "mapped_group_id", "ledger_groups", "SET NULL",
     "trial_balance_accounts_mapped_group_id_fkey"),
    ("ledger_groups", "parent_id", "ledger_groups", "SET NULL",
     "ledger_groups_parent_id_fkey"),
]

_OLD_EMAIL_CONSTRAINT = "company_users_email_key"
_EMAIL_INDEX = "uq_company_users_email_active"

# Every FK constraint currently on (table, column) — there may be more than one.
_FIND_FKS = sa.text("""
    SELECT c.conname
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE c.contype = 'f'
      AND n.nspname = current_schema()
      AND t.relname = :table
      AND c.conkey = ARRAY[(
          SELECT a.attnum FROM pg_attribute a
          WHERE a.attrelid = t.oid AND a.attname = :column AND NOT a.attisdropped
      )]::smallint[]
""")


def _respecify(table: str, column: str, referent: str, ondelete: str | None, name: str) -> None:
    """Drop every FK on table.column and recreate exactly one with `ondelete`."""
    bind = op.get_bind()
    existing = bind.execute(_FIND_FKS, {"table": table, "column": column}).scalars().all()
    for conname in existing:
        op.drop_constraint(conname, table, type_="foreignkey")
    op.create_foreign_key(name, table, referent, [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    for table, column, referent, ondelete, name in _FKS:
        _respecify(table, column, referent, ondelete, name)

    # Idempotent repair of active-only email uniqueness (see module docstring).
    op.execute(
        f'ALTER TABLE company_users DROP CONSTRAINT IF EXISTS "{_OLD_EMAIL_CONSTRAINT}"'
    )
    op.execute(
        f'CREATE UNIQUE INDEX IF NOT EXISTS "{_EMAIL_INDEX}" '
        "ON company_users (lower(email)) WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    # Restore NO ACTION on every FK touched above (the pre-purge behaviour).
    for table, column, referent, _ondelete, name in _FKS:
        _respecify(table, column, referent, None, name)
