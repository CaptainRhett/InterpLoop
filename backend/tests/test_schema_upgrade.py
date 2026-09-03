import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect

from backend.app import create_app
from backend.app.config import Config
from backend.app.models import UserAccount, db


class SchemaUpgradeTestCase(unittest.TestCase):
    def test_existing_account_table_gets_session_version_column(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY,
                        student_no VARCHAR(64),
                        name VARCHAR(120) NOT NULL,
                        role VARCHAR(20) NOT NULL,
                        created_at DATETIME NOT NULL,
                        last_login_at DATETIME
                    );
                    CREATE TABLE user_accounts (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL UNIQUE,
                        login_id VARCHAR(120) NOT NULL UNIQUE,
                        password_hash VARCHAR(512) NOT NULL,
                        is_active BOOLEAN NOT NULL,
                        must_change_password BOOLEAN NOT NULL,
                        password_changed_at DATETIME,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users (id)
                    );
                    INSERT INTO users
                        (id, name, role, created_at)
                    VALUES
                        (1, '旧管理员', 'admin', '2026-08-29 00:00:00');
                    INSERT INTO user_accounts
                        (id, user_id, login_id, password_hash, is_active,
                         must_change_password, created_at, updated_at)
                    VALUES
                        (1, 1, 'legacy-admin', 'unused', 1, 0,
                         '2026-08-29 00:00:00', '2026-08-29 00:00:00');
                    """
                )

            class LegacyConfig(Config):
                TESTING = True
                SECRET_KEY = "schema-upgrade-test"
                SQLALCHEMY_DATABASE_URI = f"sqlite:///{database_path}"
                UPLOAD_DIR = Path(temp_dir) / "uploads"

            app = create_app(LegacyConfig)
            with app.app_context():
                columns = {
                    column["name"]
                    for column in inspect(db.engine).get_columns("user_accounts")
                }
                self.assertIn("session_version", columns)
                self.assertEqual(
                    UserAccount.query.filter_by(login_id="legacy-admin")
                    .one()
                    .session_version,
                    1,
                )


if __name__ == "__main__":
    unittest.main()
