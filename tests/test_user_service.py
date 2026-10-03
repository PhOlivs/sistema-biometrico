import pytest
from werkzeug.security import generate_password_hash

from database import database
from models.user import STATUS_APPROVED, STATUS_PENDING
from services import user_service
from services.user_service import ValidationError


@pytest.fixture
def conn(tmp_path):
    connection = database.connect(str(tmp_path / "test.db"))
    database.init_db(connection)
    yield connection
    connection.close()


def create_user(conn, *, email="maria@egíde.com.br", **overrides):
    data = {
        "name": "Maria Souza",
        "birth_date": "1992-04-12",
        "cpf_encrypted": "encrypted",
        "cpf_digest": f"digest-{email}",
        "rg_encrypted": None,
        "email": email,
        "job_title": "Analista Ambiental",
        "division": "Divisão de Recursos Hídricos",
        "password_hash": generate_password_hash("SenhaForte-123!", method="scrypt"),
        "biometric_consent": True,
    }
    data.update(overrides)
    return user_service.create_pending_user(conn, **data)


def create_admin(conn):
    return user_service.create_provisioned_admin(
        conn, name="Admin Local", email="admin@egíde.com.br",
        password_hash=generate_password_hash("SenhaAdmin-123!", method="scrypt"),
    )


def add_biometrics(conn, user):
    conn.executemany(
        "INSERT INTO biometric_profiles (user_id, angle, embedding, model_version, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (user.id, angle, b"protected", "test", "2026-09-28T12:00:00+00:00")
            for angle in ("FRONT", "RIGHT", "LEFT")
        ],
    )
    conn.execute(
        "UPDATE users SET profile_photo_encrypted = ? WHERE id = ?",
        (b"protected-photo", user.id),
    )
    conn.commit()


def assign_position(conn, user, code, *, area_code="INTELLIGENCE", manager_user_id=None):
    position = conn.execute(
        "SELECT id, access_level, scope FROM organization_positions WHERE code = ?", (code,)
    ).fetchone()
    area = conn.execute(
        "SELECT id FROM organization_areas WHERE code = ?", (area_code,)
    ).fetchone() if position["scope"] == "AREA" else None
    team = conn.execute(
        "SELECT id FROM organization_teams WHERE area_id = ? ORDER BY id LIMIT 1",
        (area["id"],),
    ).fetchone() if area else None
    prefix = {1: "X", 2: "Y", 3: "Z"}[position["access_level"]]
    conn.execute(
        "UPDATE users SET position_id = ?, area_id = ?, team_id = ?, manager_user_id = ?, "
        "access_level = ?, access_level_assigned = 1, status = 'APPROVED', active = 1, "
        "matricula = ?, updated_at = created_at WHERE id = ?",
        (
            position["id"], area["id"] if area else None,
            team["id"] if team else None, manager_user_id,
            position["access_level"], f"{prefix}{user.id + 900:03}", user.id,
        ),
    )
    conn.commit()
    return user_service.get_user(conn, user.id)


def make_supervisor(conn, code, *, email):
    supervisor = create_user(conn, email=email)
    return assign_position(conn, supervisor, code)


def test_public_user_has_no_matricula_or_security_level(conn):
    first = create_user(conn)
    second = create_user(conn, email="maria2@egíde.com.br")
    assert first.matricula is None
    assert first.access_level is None
    assert not first.access_level_assigned
    assert first.status == STATUS_PENDING
    assert second.matricula is None
    assert conn.execute("SELECT last_value FROM matricula_counters WHERE access_level=1").fetchone()[0] == 0


def test_public_registration_cannot_assign_role_level_or_matricula(conn):
    user = create_user(conn)
    assert user.role == "USER"
    assert user.access_level is None
    assert user.matricula is None


@pytest.mark.parametrize("email", ["person@example.com", "person@egide.com.br", "person@egíde.com"])
def test_non_institutional_email_is_rejected(conn, email):
    with pytest.raises(ValidationError) as error:
        create_user(conn, email=email)
    assert "email" in error.value.errors


def test_institutional_email_is_normalized(conn):
    user = create_user(conn, email="Pessoa@EGÍDE.COM.BR")
    assert user.email == "pessoa@egíde.com.br"


def test_duplicate_email_and_cpf_are_rejected(conn):
    create_user(conn)
    with pytest.raises(ValidationError):
        create_user(conn, email="MARIA@egíde.com.br")
    with pytest.raises(ValidationError):
        create_user(conn, email="outra@egíde.com.br", cpf_digest="digest-maria@egíde.com.br")


def test_first_administrator_is_provisioned_explicitly(conn):
    admin = create_admin(conn)
    assert admin.role == "ADMIN"
    assert admin.status == STATUS_APPROVED
    assert admin.matricula == "Z001"
    assert admin.access_level == 3
    assert admin.area_id is not None
    assert admin.team_id is not None


def test_approval_requires_three_biometrics_and_valid_level(conn):
    admin = create_admin(conn)
    pending = create_user(conn)
    with pytest.raises(ValidationError, match="três capturas"):
        user_service.approve_user(
            conn, admin_id=admin.id, user_id=pending.id, access_level=1,
            position_code="ANALYST_I", area_id=1, team_id=1, manager_user_id=None,
        )
    add_biometrics(conn, pending)
    manager = make_supervisor(
        conn, "AGENT_I", email="agent-i@egíde.com.br"
    )
    with pytest.raises(ValidationError) as error:
        user_service.approve_user(
            conn, admin_id=admin.id, user_id=pending.id, access_level=9,
            position_code="ANALYST_I", area_id=manager.area_id,
            team_id=manager.team_id, manager_user_id=manager.id,
        )
    assert "access_level" in error.value.errors
    assert user_service.get_user(conn, pending.id).status == STATUS_PENDING


@pytest.mark.parametrize(
    "level,expected_matricula",
    [(1, "X001"), (2, "Y001"), (3, "Z002")],
)
def test_admin_assigns_level_and_system_generates_matricula(conn, level, expected_matricula):
    admin = create_admin(conn)
    pending = create_user(conn)
    add_biometrics(conn, pending)
    if level == 1:
        position_code = "ANALYST_I"
        manager = make_supervisor(conn, "AGENT_I", email="agent-i@egíde.com.br")
        area_id, team_id, manager_id = manager.area_id, manager.team_id, manager.id
    elif level == 2:
        position_code = "SPECIALIST_I"
        manager = make_supervisor(conn, "AGENT_II", email="agent-ii@egíde.com.br")
        area_id, team_id, manager_id = manager.area_id, manager.team_id, manager.id
    else:
        position_code = "EXECUTIVE_DIRECTOR"
        area_id, team_id, manager_id = admin.area_id, admin.team_id, admin.id
    approved = user_service.approve_user(
        conn, admin_id=admin.id, user_id=pending.id, access_level=level,
        position_code=position_code, area_id=area_id, team_id=team_id,
        manager_user_id=manager_id,
    )
    assert approved.status == STATUS_APPROVED
    assert approved.access_level == level
    assert approved.access_level_assigned
    assert approved.matricula == expected_matricula
    audit = conn.execute(
        "SELECT before_data, after_data FROM admin_actions WHERE target_user_id = ?",
        (pending.id,),
    ).fetchone()
    assert '"access_level": null' in audit["before_data"]
    assert f'"access_level": {level}' in audit["after_data"]
    assert f'"matricula": "{expected_matricula}"' in audit["after_data"]


def test_rejection_requires_reason_and_preserves_status_on_invalid_input(conn):
    admin = create_admin(conn)
    pending = create_user(conn)
    with pytest.raises(ValidationError):
        user_service.reject_user(conn, admin_id=admin.id, user_id=pending.id, reason=" ")
    rejected = user_service.reject_user(
        conn, admin_id=admin.id, user_id=pending.id, reason="Dados incompletos."
    )
    assert rejected.status == "REJECTED"
    assert rejected.matricula is None


def test_suspension_requires_a_reason_and_retains_user_record(conn):
    admin = create_admin(conn)
    user = create_user(conn)
    with pytest.raises(ValidationError):
        user_service.set_user_status(
            conn, admin_id=admin.id, user_id=user.id, status="SUSPENDED"
        )
    suspended = user_service.set_user_status(
        conn, admin_id=admin.id, user_id=user.id, status="SUSPENDED",
        reason="Revisão administrativa",
    )
    assert suspended.status == "SUSPENDED"
    assert user_service.get_user(conn, user.id) is not None


def test_user_search_filter_and_count(conn):
    admin = create_admin(conn)
    first = create_user(conn)
    second = create_user(conn, email="maria2@egíde.com.br")
    assert len(user_service.list_users(conn, query="maria")) == 2
    assert len(user_service.list_users(conn, level=2)) == 0
    assert len(user_service.list_users(conn, level=1)) == 0
    assert user_service.count_users(conn)["approved"] == 1
    assert user_service.count_users(conn)["pending"] == 2
    assert admin.is_admin
    assert first.status == second.status == STATUS_PENDING


def test_admin_profile_edit_cannot_assign_pending_user_level(conn):
    admin = create_admin(conn)
    user = create_user(conn)
    updated = user_service.update_user(
        conn, admin_id=admin.id, user_id=user.id,
        name=user.name, email=user.email, birth_date=user.birth_date,
        cpf_encrypted=None, cpf_digest=None, rg_encrypted=None,
        job_title=user.job_title, division=user.division, access_level="3",
    )
    assert updated.access_level is None
    assert not updated.access_level_assigned
    assert updated.matricula is None


def test_changing_approved_level_keeps_matricula_and_logs_change(conn):
    admin = create_admin(conn)
    user = create_user(conn)
    add_biometrics(conn, user)
    user = user_service.approve_user(
        conn, admin_id=admin.id, user_id=user.id, access_level=1,
        position_code="ANALYST_I", area_id=1, team_id=1,
        manager_user_id=make_supervisor(
            conn, "AGENT_I", email="agent-i@egíde.com.br"
        ).id,
    )
    matricula = user.matricula
    updated = user_service.update_user(
        conn, admin_id=admin.id, user_id=user.id,
        name=user.name, email=user.email, birth_date=user.birth_date,
        cpf_encrypted=None, cpf_digest=None, rg_encrypted=None,
        job_title=user.job_title, division=user.division, access_level=3,
        org_assignment={
            "position_code": "EXECUTIVE_DIRECTOR", "area_id": admin.area_id,
            "team_id": admin.team_id, "manager_user_id": admin.id, "access_level": 3,
        },
    )
    assert updated.matricula == matricula
    assert updated.access_level == 3
    assert conn.execute(
        "SELECT action FROM admin_actions WHERE target_user_id = ? ORDER BY id DESC",
        (user.id,),
    ).fetchone()["action"] == "ADMIN_CHANGE_LEVEL"


def test_admin_emails_must_use_institutional_domain(conn):
    with pytest.raises(ValidationError) as error:
        user_service.create_provisioned_admin(
            conn, name="Admin", email="admin@example.com",
            password_hash="protected",
        )
    assert "email" in error.value.errors
