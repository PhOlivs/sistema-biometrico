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


def create_user(conn, **overrides):
    data = {
        "name": "Maria Souza",
        "birth_date": "1992-04-12",
        "cpf_encrypted": "encrypted",
        "cpf_digest": f"digest-{overrides.get('email', 'maria@example.com')}",
        "rg_encrypted": None,
        "email": overrides.get("email", "maria@example.com"),
        "job_title": "Analista Ambiental",
        "division": "Divisão de Recursos Hídricos",
        "password_hash": generate_password_hash("SenhaForte-123!", method="scrypt"),
        "access_level": 1,
    }
    data.update(overrides)
    return user_service.create_pending_user(conn, **data)


def create_admin(conn):
    return user_service.create_provisioned_admin(
        conn, name="Admin Local", email="admin@example.com",
        password_hash=generate_password_hash("SenhaAdmin-123!", method="scrypt"),
    )


def test_public_user_is_pending_and_matricula_is_generated_by_level(conn):
    one = create_user(conn)
    two = create_user(conn, email="maria2@example.com")
    higher = create_user(conn, email="higher@example.com", access_level=3)
    assert (one.matricula, two.matricula, higher.matricula) == ("X001", "X002", "Z001")
    assert one.status == STATUS_PENDING
    assert one.role == "USER"


def test_public_registration_cannot_assign_admin_role(conn):
    assert not {"role", "status", "matricula"} <= set(
        user_service.create_pending_user.__annotations__
    )
    user = create_user(conn)
    assert user.role == "USER"


def test_duplicate_email_and_cpf_are_rejected(conn):
    create_user(conn)
    with pytest.raises(ValidationError):
        create_user(conn, email="MARIA@example.com")
    with pytest.raises(ValidationError):
        create_user(conn, email="different@example.com", cpf_digest="digest-maria@example.com")


def test_invalid_level_is_rejected(conn):
    for invalid_level in (5, True, " 1.0", "+1"):
        with pytest.raises(ValidationError) as error:
            create_user(conn, access_level=invalid_level)
        assert "access_level" in error.value.errors
    assert user_service.count_users(conn)["total"] == 0


def test_first_administrator_is_provisioned_explicitly(conn):
    admin = create_admin(conn)
    assert admin.role == "ADMIN"
    assert admin.status == STATUS_APPROVED
    assert admin.matricula == "Z001"
    assert user_service.create_pending_user


def test_approval_requires_three_biometric_captures(conn):
    admin = create_admin(conn)
    pending = create_user(conn)
    with pytest.raises(ValidationError, match="três etapas"):
        user_service.approve_user(conn, admin_id=admin.id, user_id=pending.id)
    assert user_service.get_user(conn, pending.id).status == STATUS_PENDING


def test_approval_rejection_and_admin_audit(conn):
    admin = create_admin(conn)
    pending = create_user(conn)
    conn.executemany(
        "INSERT INTO biometric_profiles (user_id, angle, embedding, model_version, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (pending.id, angle, b"protected", "test", "2026-09-28T12:00:00+00:00")
            for angle in ("FRONT", "RIGHT", "LEFT")
        ],
    )
    approved = user_service.approve_user(conn, admin_id=admin.id, user_id=pending.id)
    assert approved.status == STATUS_APPROVED
    assert conn.execute(
        "SELECT action FROM admin_actions WHERE target_user_id = ?", (pending.id,)
    ).fetchone()["action"] == "ADMIN_APPROVE_USER"


def test_rejection_requires_reason_and_preserves_status_on_invalid_input(conn):
    admin = create_admin(conn)
    pending = create_user(conn)
    with pytest.raises(ValidationError):
        user_service.reject_user(conn, admin_id=admin.id, user_id=pending.id, reason=" ")
    rejected = user_service.reject_user(
        conn, admin_id=admin.id, user_id=pending.id, reason="Dados incompletos."
    )
    assert rejected.status == "REJECTED"


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
    second = create_user(conn, email="maria2@example.com", access_level=2)
    assert len(user_service.list_users(conn, query="maria")) == 2
    assert len(user_service.list_users(conn, level=2)) == 1
    assert user_service.count_users(conn)["approved"] == 1
    assert user_service.count_users(conn)["pending"] == 2
    assert admin.is_admin
    assert first.status == second.status == STATUS_PENDING


def test_changing_access_level_keeps_matricula_and_logs_change(conn):
    admin = create_admin(conn)
    user = create_user(conn)
    matricula = user.matricula
    updated = user_service.update_user(
        conn,
        admin_id=admin.id,
        user_id=user.id,
        name=user.name,
        email=user.email,
        birth_date=user.birth_date,
        cpf_encrypted=None,
        cpf_digest=None,
        rg_encrypted=None,
        job_title=user.job_title,
        division=user.division,
        access_level=3,
    )
    assert updated.matricula == matricula
    assert updated.access_level == 3
    assert conn.execute(
        "SELECT action FROM admin_actions WHERE target_user_id = ?", (user.id,)
    ).fetchone()["action"] == "ADMIN_CHANGE_LEVEL"


def test_admin_password_and_profile_secrets_are_not_returned_on_user_model(conn):
    user = create_user(conn)
    assert not hasattr(user, "password_hash")
    assert user.cpf_encrypted == "encrypted"
