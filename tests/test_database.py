"""Testes do schema SQLite e da migração de bancos criados por versões anteriores."""

import sqlite3

from database import database
from services import user_service

# Schema exato da versão anterior (antes de cargo e divisão existirem).
OLD_SCHEMA = """
CREATE TABLE users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    email        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    role         TEXT    NOT NULL CHECK (role IN ('ADMIN', 'USER')),
    access_level INTEGER NOT NULL CHECK (access_level IN (1, 2, 3)),
    active       INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);
INSERT INTO users (name, email, role, access_level, active, created_at, updated_at)
VALUES ('Ana Lima', 'ana@example.com', 'USER', 2, 1, '2026-09-27T10:00:00', '2026-09-27T10:00:00');
"""


def column_names(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(users)")}


def test_new_database_has_job_title_and_division(tmp_path):
    conn = database.connect(str(tmp_path / "new.db"))
    database.init_db(conn)

    assert {"job_title", "division"} <= column_names(conn)
    conn.close()


def test_old_database_is_migrated_without_losing_data(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript(OLD_SCHEMA)
    assert "job_title" not in column_names(old)

    database.init_db(old)  # é o que o app faz ao iniciar
    old.close()

    conn = database.connect(path)
    assert {"job_title", "division"} <= column_names(conn)

    ana = user_service.get_user(conn, 1)
    assert ana.name == "Ana Lima"
    assert ana.email == "ana@example.com"
    assert ana.access_level == 2
    assert ana.job_title == ""      # ainda não preenchido: o admin completa na edição
    assert ana.division == ""
    conn.close()


def test_migrated_user_can_be_completed_through_the_service(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript(OLD_SCHEMA)
    database.init_db(old)
    old.close()

    conn = database.connect(path)
    updated = user_service.update_user(
        conn, 1, name="Ana Lima", email="ana@example.com",
        job_title="Diretora", division="Diretoria X", role="USER", access_level=2,
    )
    assert updated.job_title == "Diretora"
    conn.close()


def test_init_db_can_run_many_times(tmp_path):
    """O app chama init_db a cada inicialização; repetir não pode falhar nem duplicar."""
    conn = database.connect(str(tmp_path / "again.db"))
    database.init_db(conn)
    database.init_db(conn)
    database.init_db(conn)

    assert len([r for r in conn.execute("PRAGMA table_info(users)") if r[1] == "job_title"]) == 1
    conn.close()
