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
    origin TEXT NOT NULL DEFAULT '',
    appearance TEXT NOT NULL DEFAULT '',
    narrative_effects TEXT NOT NULL DEFAULT '',
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
    (1, "TOX-1101", "Verdo-A",
     "Registro cenográfico de um composto vegetal para um cenário agrícola.",
     "Desenvolvido em um cenário fictício de testes agrícolas controlados.",
     "Pó fino esverdeado (representação fictícia).",
     "Efeitos narrativos: irritação e vermelhidão cutâneas.",
     "ASTER01"),
    (1, "TOX-1102", "Hidro-L",
     "Registro cenográfico de um resíduo de processos industriais leves.",
     "Resíduo fictício de um cenário de tratamento industrial leve.",
     "Líquido transparente (representação fictícia).",
     "Efeitos narrativos: tontura e desconforto digestivo.",
     "ASTER02"),
    (1, "TOX-1103", "Agri-Tox",
     "Registro cenográfico de um material em pó associado a controle de pragas.",
     "Material fictício de um cenário agrícola de controle de pragas.",
     "Pó seco acinzentado (representação fictícia).",
     "Efeitos narrativos: irritação nasal e desconforto respiratório.",
     "ASTER03"),
    (1, "TOX-1104", "Esporina-1",
     "Registro cenográfico de esporos de um cenário de pesquisa de materiais orgânicos.",
     "Mantido em um cenário acadêmico fictício de estudo de materiais orgânicos.",
     "Pó seco (representação fictícia).",
     "Efeitos narrativos: irritação e vermelhidão ocular.",
     "ASTER04"),
    (1, "TOX-1105", "Bactox-1",
     "Registro cenográfico de um resíduo bacteriano usado em um cenário de calibração.",
     "Resíduo fictício de um cenário de calibração de sensores.",
     "Líquido turvo (representação fictícia).",
     "Efeitos narrativos: desconforto digestivo.",
     "ASTER05"),
    (2, "TOX-2101", "Necrosil-2",
     "Registro cenográfico de um composto para um cenário de testes industriais.",
     "Desenvolvido em um cenário fictício de testes de revestimentos industriais.",
     "Líquido denso amarelado (representação fictícia).",
     "Efeitos narrativos: irritação cutânea e lesões de tecidos.",
     "COBALTO01"),
    (2, "TOX-2102", "Cardionil-B",
     "Registro cenográfico de uma substância experimental de laboratório.",
     "Criado para um cenário fictício de estudos laboratoriais.",
     "Solução límpida (representação fictícia).",
     "Efeitos narrativos: tontura e alterações cardiovasculares.",
     "COBALTO02"),
    (2, "TOX-2103", "Amnesina-2",
     "Registro cenográfico de um agente volátil de um cenário acadêmico.",
     "Mantido em um cenário fictício de testes de filtros de ar.",
     "Gás leve e incolor (representação fictícia).",
     "Efeitos narrativos: confusão e alterações temporárias de memória.",
     "COBALTO03"),
    (2, "TOX-2104", "Hemoliz-C",
     "Registro cenográfico de um derivado usado em um cenário de pesquisa biomédica.",
     "Criado para um cenário fictício de estudos de hematologia.",
     "Líquido avermelhado (representação fictícia).",
     "Efeitos narrativos: palidez, fadiga e desconforto respiratório.",
     "COBALTO04"),
    (2, "TOX-2105", "Pyrotox-2",
     "Registro cenográfico de um material sintético para um cenário de ensaios térmicos.",
     "Desenvolvido em um cenário fictício de testes de materiais isolantes.",
     "Pó fino cinza (representação fictícia).",
     "Efeitos narrativos: sensação de calor e alteração da temperatura corporal.",
     "COBALTO05"),
    (3, "TOX-3101", "Vesperina-K",
     "Registro cenográfico de um composto sintético de um cenário agrícola.",
     "Criado em um cenário fictício agrícola e narrativo.",
     "Líquido volátil incolor (representação fictícia).",
     "Efeitos narrativos: tontura, alterações neurológicas e respiratórias.",
     "ORION01"),
    (3, "TOX-3102", "Omnimort-9",
     "Registro cenográfico de um agente biológico de ficção científica.",
     "Mantido em isolamento em um cenário inteiramente fictício.",
     "Gel denso e translúcido (representação fictícia).",
     "Efeitos narrativos: desconforto digestivo e comprometimento sistêmico.",
     "ORION02"),
    (3, "TOX-3103", "Bio-Destruktor",
     "Registro cenográfico de uma substância corrosiva de fantasia científica.",
     "Criado para um cenário fictício de fantasia científica.",
     "Líquido viscoso escuro (representação fictícia).",
     "Efeitos narrativos: lesões de tecidos e efeitos sistêmicos.",
     "ORION03"),
    (3, "TOX-3104", "Furia-X",
     "Registro cenográfico de um agente de um cenário narrativo.",
     "Formulado em um cenário inteiramente fictício de ficção científica.",
     "Gás invisível (representação fictícia).",
     "Efeitos narrativos: agitação, confusão e colapso físico.",
     "ORION04"),
    (3, "TOX-3105", "Necroflux-3",
     "Registro cenográfico de um composto sintético de pesquisa avançada.",
     "Criado para um cenário fictício de pesquisa avançada.",
     "Pó denso acinzentado (representação fictícia).",
     "Efeitos narrativos: fraqueza e alterações cutâneas e imunológicas.",
     "ORION05"),
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


def _add_toxin_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(toxins)")}
    for column in ("origin", "appearance", "narrative_effects"):
        if column not in existing:
            conn.execute(
                f"ALTER TABLE toxins ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
            )


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
    _add_toxin_columns(conn)
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
    for level, code, name, description, origin, appearance, effects, legacy_code in _TOXINS:
        migrated = conn.execute(
            "UPDATE toxins SET code = ?, name = ?, access_level = ?, description = ?, "
            "origin = ?, appearance = ?, narrative_effects = ? "
            "WHERE code = ?",
            (code, name, level, description, origin, appearance, effects, legacy_code),
        )
        if not migrated.rowcount:
            migrated = conn.execute(
                "UPDATE toxins SET name = ?, access_level = ?, description = ?, "
                "origin = ?, appearance = ?, narrative_effects = ? WHERE code = ?",
                (name, level, description, origin, appearance, effects, code),
            )
        if not migrated.rowcount:
            conn.execute(
                "INSERT OR IGNORE INTO toxins("
                "code, name, access_level, description, origin, appearance, narrative_effects"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (code, name, level, description, origin, appearance, effects),
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
