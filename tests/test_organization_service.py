import pytest
from werkzeug.security import generate_password_hash

from database import database
from services import organization_service, user_service


@pytest.fixture
def conn(tmp_path):
    connection = database.connect(str(tmp_path / "organization.db"))
    database.init_db(connection)
    yield connection
    connection.close()


def new_user(conn, email):
    return user_service.create_pending_user(
        conn,
        name=email.split("@")[0],
        birth_date="1990-01-01",
        cpf_encrypted=None,
        cpf_digest=None,
        rg_encrypted=None,
        email=email,
        job_title="A definir",
        division="A definir",
        password_hash=generate_password_hash("SenhaValida-123!", method="scrypt"),
        biometric_consent=True,
    )


def assign_user(conn, user, code, *, area_code="INTELLIGENCE", manager_id=None):
    position = conn.execute(
        "SELECT id, access_level, scope FROM organization_positions WHERE code = ?", (code,)
    ).fetchone()
    area = conn.execute(
        "SELECT id FROM organization_areas WHERE code = ?", (area_code,)
    ).fetchone()
    team = conn.execute(
        "SELECT id FROM organization_teams WHERE area_id = ? ORDER BY id LIMIT 1",
        (area["id"],),
    ).fetchone()
    prefix = {1: "X", 2: "Y", 3: "Z"}[position["access_level"]]
    conn.execute(
        "UPDATE users SET position_id = ?, area_id = ?, team_id = ?, manager_user_id = ?, "
        "access_level = ?, access_level_assigned = 1, status = 'APPROVED', active = 1, "
        "matricula = ?, job_title = (SELECT name FROM organization_positions WHERE id = ?), "
        "updated_at = created_at WHERE id = ?",
        (
            position["id"], area["id"], team["id"], manager_id, position["access_level"],
            f"{prefix}{user.id + 900:03}", position["id"], user.id,
        ),
    )
    conn.commit()
    return user_service.get_user(conn, user.id)


def assignment(
    conn, *, position_code, area_id, team_id, manager_user_id,
    level=None, target_id=None,
):
    return organization_service.validate_assignment(
        conn,
        position_code=position_code,
        area_id=area_id,
        team_id=team_id,
        manager_user_id=manager_user_id,
        access_level=level,
        target_user_id=target_id,
    )


def test_position_level_and_reporting_rules_are_enforced(conn):
    director = user_service.create_provisioned_admin(
        conn,
        name="Chefe",
        email="chefe@egíde.com.br",
        password_hash=generate_password_hash("SenhaAdmin-123!", method="scrypt"),
    )
    area = conn.execute(
        "SELECT id FROM organization_areas WHERE code = 'INTELLIGENCE'"
    ).fetchone()["id"]
    team = conn.execute(
        "SELECT id FROM organization_teams WHERE area_id = ?", (area,)
    ).fetchone()["id"]
    with pytest.raises(organization_service.OrganizationError) as missing_assignment:
        assignment(
            conn, position_code="EXECUTIVE_DIRECTOR", area_id=None, team_id=None,
            manager_user_id=director.id, level=3,
        )
    assert "area_id" in missing_assignment.value.errors
    assert "team_id" in missing_assignment.value.errors
    with pytest.raises(organization_service.OrganizationError) as mismatch:
        assignment(
            conn, position_code="AGENT_II", area_id=area, team_id=team,
            manager_user_id=director.id, level=1,
        )
    assert "access_level" in mismatch.value.errors
    assert "manager_user_id" in mismatch.value.errors

    agent_iii = assign_user(conn, new_user(conn, "agent3@egíde.com.br"), "AGENT_III", manager_id=director.id)
    with pytest.raises(organization_service.OrganizationError) as wrong_parent:
        assignment(
            conn, position_code="ANALYST_I", area_id=area, team_id=team,
            manager_user_id=agent_iii.id, level=1,
        )
    assert "manager_user_id" in wrong_parent.value.errors


def test_position_determines_access_level_when_admin_omits_level(conn):
    agent_i = assign_user(
        conn, new_user(conn, "agent-i-level@egíde.com.br"), "AGENT_I"
    )
    assignment_result = assignment(
        conn,
        position_code="ANALYST_II",
        area_id=agent_i.area_id,
        team_id=agent_i.team_id,
        manager_user_id=agent_i.id,
    )
    assert assignment_result["access_level"] == 1


def test_area_boundary_and_team_area_are_enforced(conn):
    agent_i = assign_user(
        conn, new_user(conn, "agent1@egíde.com.br"), "AGENT_I"
    )
    operations_area = conn.execute(
        "SELECT id FROM organization_areas WHERE code = 'OPERATIONS'"
    ).fetchone()["id"]
    operations_team = conn.execute(
        "SELECT id FROM organization_teams WHERE area_id = ?", (operations_area,)
    ).fetchone()["id"]
    with pytest.raises(organization_service.OrganizationError) as cross_area:
        assignment(
            conn, position_code="ANALYST_I", area_id=operations_area,
            team_id=operations_team, manager_user_id=agent_i.id, level=1,
        )
    assert "manager_user_id" in cross_area.value.errors

    intelligence_area = agent_i.area_id
    with pytest.raises(organization_service.OrganizationError) as wrong_team:
        assignment(
            conn, position_code="ANALYST_I", area_id=intelligence_area,
            team_id=operations_team, manager_user_id=agent_i.id, level=1,
        )
    assert "team_id" in wrong_team.value.errors


def test_operational_supervisor_must_belong_to_the_same_team(conn):
    supervisor = assign_user(
        conn, new_user(conn, "same-area-different-team@egíde.com.br"), "AGENT_I"
    )
    area_id = supervisor.area_id
    conn.execute(
        "INSERT INTO organization_teams(area_id, code, name) "
        "VALUES (?, 'INTELLIGENCE_COUNTER', 'Contrainteligência')",
        (area_id,),
    )
    other_team_id = conn.execute(
        "SELECT id FROM organization_teams WHERE code = 'INTELLIGENCE_COUNTER'"
    ).fetchone()["id"]
    with pytest.raises(organization_service.OrganizationError) as error:
        assignment(
            conn, position_code="ANALYST_I", area_id=area_id,
            team_id=other_team_id, manager_user_id=supervisor.id,
        )
    assert "mesma equipe" in error.value.errors["manager_user_id"]


def test_reporting_cycle_is_rejected(conn):
    agent_i = new_user(conn, "agent-cycle@egíde.com.br")
    analyst = new_user(conn, "analyst-cycle@egíde.com.br")
    agent_i = assign_user(conn, agent_i, "AGENT_I", manager_id=analyst.id)
    analyst = assign_user(conn, analyst, "ANALYST_I", manager_id=agent_i.id)
    with pytest.raises(organization_service.OrganizationError) as error:
        assignment(
            conn, position_code="ANALYST_II", area_id=analyst.area_id,
            team_id=analyst.team_id, manager_user_id=agent_i.id, level=1,
            target_id=analyst.id,
        )
    assert "ciclo" in error.value.errors["manager_user_id"]


def test_position_change_cannot_leave_subordinates_under_an_invalid_role(conn):
    manager = assign_user(
        conn, new_user(conn, "agent2-manager@egíde.com.br"), "AGENT_II"
    )
    assign_user(
        conn, new_user(conn, "specialist@egíde.com.br"), "SPECIALIST_I",
        manager_id=manager.id,
    )
    position = conn.execute(
        "SELECT id FROM organization_positions WHERE code = 'SPECIALIST_II'"
    ).fetchone()
    with pytest.raises(organization_service.OrganizationError) as error:
        organization_service.validate_direct_reports(
            conn, user_id=manager.id, new_position_id=position["id"],
            new_position_scope="AREA",
            new_area_id=manager.area_id,
            new_team_id=manager.team_id,
        )
    assert "subordinados atuais" in error.value.errors["position_code"]


def test_area_manager_cannot_move_teams_while_retaining_direct_reports(conn):
    manager = assign_user(
        conn, new_user(conn, "agent2-team-change@egíde.com.br"), "AGENT_II"
    )
    assign_user(
        conn, new_user(conn, "specialist-team-change@egíde.com.br"), "SPECIALIST_I",
        manager_id=manager.id,
    )
    conn.execute(
        "INSERT INTO organization_teams(area_id, code, name) "
        "VALUES (?, 'INTELLIGENCE_COUNTER', 'Contrainteligência')",
        (manager.area_id,),
    )
    new_team_id = conn.execute(
        "SELECT id FROM organization_teams WHERE code = 'INTELLIGENCE_COUNTER'"
    ).fetchone()["id"]
    position_id = conn.execute(
        "SELECT id FROM organization_positions WHERE code = 'AGENT_II'"
    ).fetchone()["id"]
    with pytest.raises(organization_service.OrganizationError) as error:
        organization_service.validate_direct_reports(
            conn, user_id=manager.id, new_position_id=position_id,
            new_position_scope="AREA", new_area_id=manager.area_id,
            new_team_id=new_team_id,
        )
    assert "equipe" in error.value.errors["team_id"]


def test_org_chart_is_built_from_assigned_database_relationships(conn):
    chief = user_service.create_provisioned_admin(
        conn,
        name="Chefe",
        email="chefe@egíde.com.br",
        password_hash=generate_password_hash("SenhaAdmin-123!", method="scrypt"),
    )
    executive = assign_user(
        conn, new_user(conn, "exec@egíde.com.br"), "EXECUTIVE_DIRECTOR",
        manager_id=chief.id,
    )
    general = assign_user(
        conn, new_user(conn, "dg@egíde.com.br"), "DIRECTOR_GENERAL",
        manager_id=executive.id,
    )
    intel_manager = assign_user(
        conn, new_user(conn, "intel-manager@egíde.com.br"), "MANAGER",
        area_code="INTELLIGENCE", manager_id=general.id,
    )
    tech_manager = assign_user(
        conn, new_user(conn, "tech-manager@egíde.com.br"), "MANAGER",
        area_code="TECHNOLOGY", manager_id=general.id,
    )
    intel_agent = assign_user(
        conn, new_user(conn, "intel-agent@egíde.com.br"), "AGENT_III",
        area_code="INTELLIGENCE", manager_id=intel_manager.id,
    )
    intel_analyst = assign_user(
        conn, new_user(conn, "intel-analyst@egíde.com.br"), "ANALYST_II",
        area_code="INTELLIGENCE", manager_id=assign_user(
            conn, new_user(conn, "intel-agent1@egíde.com.br"), "AGENT_I",
            area_code="INTELLIGENCE", manager_id=assign_user(
                conn, new_user(conn, "intel-agent2@egíde.com.br"), "AGENT_II",
                area_code="INTELLIGENCE", manager_id=intel_agent.id,
            ).id,
        ).id,
    )
    chart = organization_service.get_org_chart(conn)
    root = next(node for node in chart["roots"] if node["user"].id == chief.id)
    executive_node = root["children"][0]
    director_node = executive_node["children"][0]
    area_names = {node["user"].area_name for node in director_node["children"]}
    assert area_names == {"Inteligência", "Tecnologia e Sistemas"}
    intel_node = next(
        node for node in director_node["children"]
        if node["user"].area_name == "Inteligência"
    )
    assert intel_node["children"][0]["user"].area_name == "Inteligência"
    assert intel_analyst.manager_name is not None
    assert len(chart["unassigned"]) == 0
