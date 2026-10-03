"""Seed data for the data-backed organization structure."""

AREAS = (
    ("INTELLIGENCE", "Inteligência", "INTELLIGENCE_ANALYSIS", "Inteligência e Análise"),
    ("OPERATIONS", "Operações", "SPECIAL_OPERATIONS", "Operações Especiais"),
    ("SECURITY", "Segurança", "INSTITUTIONAL_PROTECTION", "Proteção Institucional"),
    ("TECHNOLOGY", "Tecnologia e Sistemas", "SYSTEMS_BIOMETRICS", "Sistemas e Biometria"),
    ("ADMINISTRATION", "Administrativa", "ADMIN_RESOURCES", "Administração e Recursos"),
)

POSITIONS = (
    ("CHIEF_OF_STAFF", "Chefe de Estado-Maior", 3, "GLOBAL", 10),
    ("EXECUTIVE_DIRECTOR", "Diretor Executivo", 3, "GLOBAL", 20),
    ("DIRECTOR_GENERAL", "Diretor-Geral", 3, "GLOBAL", 30),
    ("MANAGER", "Gerente", 3, "AREA", 40),
    ("AGENT_III", "Agente III", 3, "AREA", 50),
    ("AGENT_II", "Agente II", 2, "AREA", 60),
    ("AGENT_I", "Agente I", 1, "AREA", 70),
    ("ANALYST_I", "Analista I", 1, "AREA", 80),
    ("ANALYST_II", "Analista II", 1, "AREA", 90),
    ("ANALYST_III", "Analista III", 1, "AREA", 100),
    ("SPECIALIST_I", "Especialista I", 2, "AREA", 80),
    ("SPECIALIST_II", "Especialista II", 2, "AREA", 90),
    ("SPECIALIST_III", "Especialista III", 2, "AREA", 100),
)

POSITION_REPORTS = (
    ("CHIEF_OF_STAFF", "EXECUTIVE_DIRECTOR"),
    ("EXECUTIVE_DIRECTOR", "DIRECTOR_GENERAL"),
    ("DIRECTOR_GENERAL", "MANAGER"),
    ("MANAGER", "AGENT_III"),
    ("AGENT_III", "AGENT_II"),
    ("AGENT_II", "AGENT_I"),
    ("AGENT_II", "SPECIALIST_I"),
    ("AGENT_II", "SPECIALIST_II"),
    ("AGENT_II", "SPECIALIST_III"),
    ("AGENT_I", "ANALYST_I"),
    ("AGENT_I", "ANALYST_II"),
    ("AGENT_I", "ANALYST_III"),
)


def seed_organization(conn) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO organization_areas(code, name) VALUES (?, ?)",
        ((code, name) for code, name, _team_code, _team_name in AREAS),
    )
    area_ids = {
        row["code"]: row["id"]
        for row in conn.execute("SELECT id, code FROM organization_areas")
    }
    conn.executemany(
        "INSERT OR IGNORE INTO organization_teams(area_id, code, name) VALUES (?, ?, ?)",
        (
            (area_ids[area_code], team_code, team_name)
            for area_code, _name, team_code, team_name in AREAS
        ),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO organization_positions(code, name, access_level, scope, sort_order) "
        "VALUES (?, ?, ?, ?, ?)",
        POSITIONS,
    )
    position_ids = {
        row["code"]: row["id"]
        for row in conn.execute("SELECT id, code FROM organization_positions")
    }
    conn.executemany(
        "INSERT OR IGNORE INTO organization_position_reports("
        "supervisor_position_id, subordinate_position_id) VALUES (?, ?)",
        (
            (position_ids[supervisor], position_ids[subordinate])
            for supervisor, subordinate in POSITION_REPORTS
        ),
    )
    conn.execute(
        "UPDATE users SET position_id = (SELECT id FROM organization_positions "
        "WHERE code = 'CHIEF_OF_STAFF') "
        "WHERE role = 'ADMIN' AND status = 'APPROVED' AND access_level = 3 "
        "AND position_id IS NULL"
    )
    conn.execute(
        "UPDATE users SET "
        "area_id = (SELECT id FROM organization_areas WHERE code = 'ADMINISTRATION'), "
        "team_id = (SELECT id FROM organization_teams WHERE code = 'ADMIN_RESOURCES') "
        "WHERE role = 'ADMIN' AND status = 'APPROVED' AND access_level = 3 "
        "AND position_id = (SELECT id FROM organization_positions WHERE code = 'CHIEF_OF_STAFF') "
        "AND (area_id IS NULL OR team_id IS NULL)"
    )
