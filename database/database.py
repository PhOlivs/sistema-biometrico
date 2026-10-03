"""SQLite persistence, schema creation and legacy database migration."""

import os
import re
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g

from models.organization import seed_organization

SCHEMA = """
CREATE TABLE IF NOT EXISTS security_levels (
    level INTEGER PRIMARY KEY CHECK (level BETWEEN 1 AND 3),
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS organization_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS organization_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area_id INTEGER NOT NULL REFERENCES organization_areas(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    UNIQUE (area_id, code),
    UNIQUE (area_id, name),
    UNIQUE (area_id, id)
);

CREATE TABLE IF NOT EXISTS organization_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    access_level INTEGER NOT NULL REFERENCES security_levels(level),
    scope TEXT NOT NULL CHECK (scope IN ('GLOBAL', 'AREA')),
    sort_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS organization_position_reports (
    supervisor_position_id INTEGER NOT NULL REFERENCES organization_positions(id),
    subordinate_position_id INTEGER NOT NULL REFERENCES organization_positions(id),
    PRIMARY KEY (supervisor_position_id, subordinate_position_id),
    CHECK (supervisor_position_id != subordinate_position_id)
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula TEXT UNIQUE,
    name TEXT NOT NULL,
    birth_date TEXT,
    cpf_encrypted TEXT,
    cpf_digest TEXT UNIQUE,
    rg_encrypted TEXT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    job_title TEXT NOT NULL DEFAULT '',
    division TEXT NOT NULL DEFAULT '',
    position_id INTEGER REFERENCES organization_positions(id),
    area_id INTEGER REFERENCES organization_areas(id),
    team_id INTEGER REFERENCES organization_teams(id),
    manager_user_id INTEGER REFERENCES users(id),
    profile_photo_encrypted BLOB,
    biometric_photo_consent_at TEXT,
    password_hash TEXT,
    role TEXT NOT NULL DEFAULT 'USER' CHECK (role IN ('ADMIN', 'USER')),
    access_level INTEGER NOT NULL CHECK (access_level IN (1, 2, 3)),
    access_level_assigned INTEGER NOT NULL DEFAULT 0 CHECK (access_level_assigned IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'SUSPENDED', 'INACTIVE')),
    rejection_reason TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_activity_at TEXT,
    deleted_at TEXT,
    FOREIGN KEY (access_level) REFERENCES security_levels(level),
    FOREIGN KEY (area_id, team_id) REFERENCES organization_teams(area_id, id)
);

CREATE TABLE IF NOT EXISTS matricula_counters (
    access_level INTEGER PRIMARY KEY REFERENCES security_levels(level),
    last_value INTEGER NOT NULL DEFAULT 0 CHECK (last_value >= 0)
);

CREATE TABLE IF NOT EXISTS biometric_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    angle TEXT NOT NULL CHECK (angle IN ('FRONT', 'RIGHT', 'LEFT')),
    embedding BLOB NOT NULL,
    model_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, angle)
);

CREATE TABLE IF NOT EXISTS toxins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    access_level INTEGER NOT NULL REFERENCES security_levels(level),
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ATIVO' CHECK (status IN ('ATIVO', 'ARQUIVADO'))
);

CREATE TABLE IF NOT EXISTS access_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    matricula TEXT,
    event TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('SUCCESS', 'DENIED', 'FAILURE', 'INFO')),
    resource_id INTEGER REFERENCES toxins(id) ON DELETE SET NULL,
    required_level INTEGER,
    auth_type TEXT,
    details TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    target_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    before_data TEXT,
    after_data TEXT,
    reason TEXT,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);

"""

_LEGACY_COLUMNS = {
    "matricula": "TEXT",
    "birth_date": "TEXT",
    "cpf_encrypted": "TEXT",
    "cpf_digest": "TEXT",
    "rg_encrypted": "TEXT",
    "password_hash": "TEXT",
    "status": "TEXT NOT NULL DEFAULT 'PENDING'",
    "rejection_reason": "TEXT",
    "approved_by": "INTEGER REFERENCES users(id)",
    "approved_at": "TEXT",
    "last_activity_at": "TEXT",
    "deleted_at": "TEXT",
    "access_level_assigned": "INTEGER NOT NULL DEFAULT 1 CHECK (access_level_assigned IN (0, 1))",
    "profile_photo_encrypted": "BLOB",
    "biometric_photo_consent_at": "TEXT",
    "position_id": "INTEGER REFERENCES organization_positions(id)",
    "area_id": "INTEGER REFERENCES organization_areas(id)",
    "team_id": "INTEGER REFERENCES organization_teams(id)",
    "manager_user_id": "INTEGER REFERENCES users(id)",
}
_PREFIXES = {1: "X", 2: "Y", 3: "Z"}
_MATRICULA_PATTERN = re.compile(r"^[XYZ](\d{3,})$")
_TOXINS = (
    (1, "Aster-01", "Registro cenográfico de acesso geral; conteúdo fictício e não operacional."),
    (1, "Aster-02", "Ficha acadêmica fictícia para demonstração de autorização."),
    (1, "Aster-03", "Registro demonstrativo sem dados químicos reais."),
    (1, "Aster-04", "Artefato de catálogo cenográfico para testes de interface."),
    (1, "Aster-05", "Registro fictício destinado a demonstrar consultas autorizadas."),
    (2, "Cobalto-01", "Dossiê de cenário fictício; não contém instruções ou dados de produção."),
    (2, "Cobalto-02", "Registro acadêmico sintético de classificação intermediária."),
    (2, "Cobalto-03", "Ficha cenográfica para validar filtros e auditoria."),
    (2, "Cobalto-04", "Descrição deliberadamente não acionável para apresentação acadêmica."),
    (2, "Cobalto-05", "Registro fictício para demonstração do controle hierárquico."),
    (3, "Orion-01", "Dossiê cenográfico de acesso superior, sem informação técnica real."),
    (3, "Orion-02", "Registro fictício para demonstrar permissões de nível máximo."),
    (3, "Orion-03", "Ficha acadêmica sintética; não representa substância existente."),
    (3, "Orion-04", "Conteúdo demonstrativo sem dados de aquisição, síntese ou uso."),
    (3, "Orion-05", "Registro inteiramente fictício para apresentação do protótipo."),
)


def connect(path: str) -> sqlite3.Connection:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _add_legacy_columns(conn: sqlite3.Connection) -> tuple[bool, bool]:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    had_status_column = "status" in existing
    had_level_assignment_column = "access_level_assigned" in existing
    for column, definition in _LEGACY_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
    return not had_status_column, not had_level_assignment_column


def _migrate_legacy_users(
    conn: sqlite3.Connection, migrate_status: bool, migrate_level_assignment: bool
) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT id, access_level, role, active, matricula, status FROM users ORDER BY id"
    ).fetchall()
    counters = {1: 0, 2: 0, 3: 0}
    for row in rows:
        level = row["access_level"] if row["access_level"] in _PREFIXES else 1
        existing = row["matricula"]
        if existing and _MATRICULA_PATTERN.fullmatch(existing):
            counters[level] = max(counters[level], int(existing[1:]))
        elif existing:
            existing = None
        if not existing and migrate_level_assignment:
            counters[level] += 1
            existing = f"{_PREFIXES[level]}{counters[level]:03d}"

        status = row["status"]
        if migrate_status:
            if row["role"] == "ADMIN":
                status = "INACTIVE"
            else:
                status = "APPROVED" if row["active"] else "SUSPENDED"
        conn.execute(
            "UPDATE users SET matricula = ?, status = ?, active = ?, "
            "access_level_assigned = CASE WHEN ? THEN 1 ELSE access_level_assigned END, "
            "updated_at = COALESCE(updated_at, ?) "
            "WHERE id = ?",
            (existing, status, int(status in ("APPROVED", "PENDING")) if migrate_status
             else row["active"], int(migrate_level_assignment), now, row["id"]),
        )
    for level, value in counters.items():
        conn.execute(
            "INSERT INTO matricula_counters(access_level, last_value) VALUES (?, ?) "
            "ON CONFLICT(access_level) DO UPDATE SET last_value = MAX(last_value, excluded.last_value)",
            (level, value),
        )


def init_db(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    migrate_status, migrate_level_assignment = _add_legacy_columns(conn)
    conn.executemany(
        "INSERT OR IGNORE INTO security_levels(level, name) VALUES (?, ?)",
        ((1, "Acesso geral"), (2, "Acesso de diretoria"), (3, "Acesso ministerial")),
    )
    seed_organization(conn)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
        CREATE INDEX IF NOT EXISTS idx_users_level ON users(access_level);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_matricula ON users(matricula);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_cpf_digest ON users(cpf_digest);
        CREATE INDEX IF NOT EXISTS idx_users_org_position ON users(position_id, area_id, team_id);
        CREATE INDEX IF NOT EXISTS idx_users_org_manager ON users(manager_user_id);
        CREATE INDEX IF NOT EXISTS idx_access_logs_created ON access_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_access_logs_event_result ON access_logs(event, result);
        CREATE INDEX IF NOT EXISTS idx_admin_actions_created ON admin_actions(created_at DESC);
        """
    )
    conn.executemany(
        "INSERT OR IGNORE INTO matricula_counters(access_level, last_value) VALUES (?, 0)",
        ((1,), (2,), (3,)),
    )
    _migrate_legacy_users(conn, migrate_status, migrate_level_assignment)
    conn.executemany(
        "INSERT OR IGNORE INTO toxins(code, name, access_level, description) VALUES (?, ?, ?, ?)",
        ((f"{name.upper().replace('-', '')}", name, level, description)
         for level, name, description in _TOXINS),
    )
    conn.commit()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_error=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
