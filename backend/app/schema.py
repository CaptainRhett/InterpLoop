from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from .models import db


def _column_names(table_name):
    inspector = inspect(db.engine)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade_schema():
    """Apply small, idempotent compatibility upgrades for existing databases."""
    applied = []
    if "session_version" not in _column_names("user_accounts"):
        try:
            with db.engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE user_accounts "
                        "ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1"
                    )
                )
        except OperationalError:
            # Multiple application workers may attempt the same startup upgrade.
            # Ignore the race only when another worker has successfully added it.
            if "session_version" not in _column_names("user_accounts"):
                raise
        applied.append("user_accounts.session_version")
    return applied
