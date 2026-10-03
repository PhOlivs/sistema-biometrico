import sqlite3

from database import database
from services import user_service


OLD_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    job_title TEXT NOT NULL DEFAULT '',
    division TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL CHECK (role IN ('ADMIN', 'USER')),
    access_level INTEGER NOT NULL CHECK (access_level IN (1, 2, 3)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
INSERT INTO users (name, email, role, access_level, active, created_at, updated_at)
VALUES ('Ana Lima', 'ana@example.com', 'USER', 2, 1, '2026-09-27T10:00:00', '2026-09-27T10:00:00');
"""


def test_new_database_has_domain_tables_and_fifteen_fictional_records(tmp_path):
    conn = database.connect(str(tmp_path / "new.db"))
    database.init_db(conn)
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {
        "users", "security_levels", "matricula_counters", "biometric_profiles",
        "toxins", "access_logs", "admin_actions", "organization_areas",
        "organization_teams", "organization_positions", "organization_position_reports",
    } <= tables
    assert conn.execute("SELECT COUNT(*) FROM toxins").fetchone()[0] == 15
    assert conn.execute("SELECT COUNT(*) FROM organization_areas").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM organization_teams").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM organization_positions").fetchone()[0] == 13
    conn.close()


def test_legacy_database_migrates_users_and_assigns_unique_matricula(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript(OLD_SCHEMA)
    database.init_db(old)
    old.close()

    conn = database.connect(path)
    ana = user_service.get_user(conn, 1)
    assert ana.name == "Ana Lima"
    assert ana.email == "ana@example.com"
    assert ana.access_level == 2
    assert ana.matricula == "Y001"
    assert ana.status == "APPROVED"
    conn.close()


def test_legacy_administrator_gets_an_organizational_assignment(tmp_path):
    conn = database.connect(str(tmp_path / "old-admin.db"))
    database.init_db(conn)
    conn.execute(
        """
        INSERT INTO users (
            name, email, job_title, division, role, access_level,
            access_level_assigned, status, active, created_at, updated_at
        ) VALUES ('Admin antigo', 'admin@example.com', '', '', 'ADMIN', 3, 1,
                  'APPROVED', 1, '2026-09-27T10:00:00', '2026-09-27T10:00:00')
        """
    )
    conn.commit()
    database.init_db(conn)
    admin = user_service.get_user(conn, 1)
    assert admin.position_id is not None
    assert admin.area_id is not None
    assert admin.team_id is not None
    conn.close()


def test_init_db_is_idempotent(tmp_path):
    conn = database.connect(str(tmp_path / "again.db"))
    database.init_db(conn)
    database.init_db(conn)
    database.init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM toxins").fetchone()[0] == 15
    assert conn.execute("SELECT COUNT(*) FROM security_levels").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM organization_areas").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM organization_positions").fetchone()[0] == 13
    conn.close()
