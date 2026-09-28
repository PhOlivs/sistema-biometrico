"""
Testes das regras de negócio de usuários (services/user_service.py).

Cada teste usa um banco SQLite temporário (tmp_path), então o banco
real database/bioauth.db nunca é tocado.
"""

import sqlite3

import pytest

from database import database
from services import user_service
from services.user_service import UserNotFoundError, ValidationError


@pytest.fixture
def conn(tmp_path):
    connection = database.connect(str(tmp_path / "test.db"))
    database.init_db(connection)
    yield connection
    connection.close()


def valid_data(**overrides):
    data = {
        "name": "Maria Souza",
        "email": "maria@example.com",
        "job_title": "Analista Ambiental",
        "division": "Divisão de Recursos Hídricos",
        "role": "USER",
        "access_level": 1,
    }
    data.update(overrides)
    return data


def make_user(conn, **overrides):
    return user_service.create_user(conn, **valid_data(**overrides))


def edit_user(conn, user, **overrides):
    """Atualiza `user` mantendo os valores atuais, exceto os informados."""
    data = {
        "name": user.name,
        "email": user.email,
        "job_title": user.job_title,
        "division": user.division,
        "role": user.role,
        "access_level": user.access_level,
    }
    data.update(overrides)
    return user_service.update_user(conn, user.id, **data)


# ----------------------------------------------------------------------
# Criação
# ----------------------------------------------------------------------

def test_create_user_saves_data_and_starts_active(conn):
    user = make_user(conn, access_level=2)

    assert user.id is not None
    assert user.name == "Maria Souza"
    assert user.email == "maria@example.com"
    assert user.job_title == "Analista Ambiental"
    assert user.division == "Divisão de Recursos Hídricos"
    assert user.role == "USER"
    assert user.access_level == 2
    assert user.active is True
    assert user.created_at and user.updated_at


def test_create_user_trims_text_and_normalizes_email(conn):
    user = make_user(
        conn,
        name="  Maria Souza  ",
        email="  Maria@Example.COM ",
        job_title="  Analista  ",
        division="  Divisão X ",
    )
    assert user.name == "Maria Souza"
    assert user.email == "maria@example.com"
    assert user.job_title == "Analista"
    assert user.division == "Divisão X"


def test_create_user_accepts_level_as_text_from_form(conn):
    assert make_user(conn, access_level="3").access_level == 3


def test_create_requires_named_arguments(conn):
    """Evita trocar cargo por divisão (ou e-mail por nome) por engano de ordem."""
    with pytest.raises(TypeError):
        user_service.create_user(conn, "Maria", "m@example.com", "Cargo", "Divisão", "USER", 1)


@pytest.mark.parametrize("role", ["ADMIN", "USER"])
def test_valid_roles(conn, role):
    assert make_user(conn, role=role).role == role


@pytest.mark.parametrize("role", ["", "admin", "SUPERUSER", "ROOT", None])
def test_invalid_role_is_rejected(conn, role):
    with pytest.raises(ValidationError) as exc:
        make_user(conn, role=role)
    assert "role" in exc.value.errors


@pytest.mark.parametrize("level", [1, 2, 3])
def test_valid_levels(conn, level):
    assert make_user(conn, access_level=level).access_level == level


@pytest.mark.parametrize("level", [0, 4, 999, -1, "abc", "", "1.5", None, True])
def test_invalid_level_is_rejected(conn, level):
    with pytest.raises(ValidationError) as exc:
        make_user(conn, access_level=level)
    assert "access_level" in exc.value.errors


def test_admin_with_invalid_level_is_rejected(conn):
    """Administrador não ganha 'nível 999': o nível continua precisando ser 1, 2 ou 3."""
    with pytest.raises(ValidationError) as exc:
        make_user(conn, role="ADMIN", access_level=999)
    assert "access_level" in exc.value.errors


def test_admin_keeps_a_regular_access_level(conn):
    admin = make_user(conn, role="ADMIN", access_level=3)
    assert admin.is_admin
    assert admin.access_level == 3


@pytest.mark.parametrize("field", ["name", "job_title", "division"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_required_text_fields(conn, field, value):
    with pytest.raises(ValidationError) as exc:
        make_user(conn, **{field: value})
    assert field in exc.value.errors


@pytest.mark.parametrize("field", ["name", "job_title", "division"])
def test_text_fields_have_a_maximum_length(conn, field):
    with pytest.raises(ValidationError) as exc:
        make_user(conn, **{field: "x" * 121})
    assert field in exc.value.errors


@pytest.mark.parametrize("email", ["", None, "sem-arroba", "a@b", "a b@c.com", "@c.com"])
def test_invalid_email_is_rejected(conn, email):
    with pytest.raises(ValidationError) as exc:
        make_user(conn, email=email)
    assert "email" in exc.value.errors


def test_all_errors_are_reported_together(conn):
    with pytest.raises(ValidationError) as exc:
        user_service.create_user(
            conn, name="", email="invalido", job_title="", division="", role="XYZ", access_level=999
        )
    assert set(exc.value.errors) == {
        "name", "email", "job_title", "division", "role", "access_level",
    }


def test_duplicate_email_is_rejected(conn):
    make_user(conn, email="maria@example.com")
    with pytest.raises(ValidationError) as exc:
        make_user(conn, name="Outra Pessoa", email="maria@example.com")
    assert "email" in exc.value.errors


def test_duplicate_email_ignores_letter_case(conn):
    make_user(conn, email="maria@example.com")
    with pytest.raises(ValidationError):
        make_user(conn, name="Outra Pessoa", email="MARIA@EXAMPLE.COM")


def test_invalid_data_does_not_create_a_row(conn):
    with pytest.raises(ValidationError):
        make_user(conn, access_level=999)
    assert user_service.count_users(conn)["total"] == 0


# ----------------------------------------------------------------------
# Edição
# ----------------------------------------------------------------------

def test_update_changes_access_level(conn):
    user = make_user(conn, access_level=1)
    assert edit_user(conn, user, access_level=3).access_level == 3


def test_update_changes_job_title_and_division(conn):
    user = make_user(conn)
    updated = edit_user(conn, user, job_title="Diretor", division="Diretoria de Recursos Naturais")
    assert updated.job_title == "Diretor"
    assert updated.division == "Diretoria de Recursos Naturais"


def test_update_changes_role_when_another_admin_exists(conn):
    make_user(conn, name="Admin Um", email="um@example.com", role="ADMIN", access_level=3)
    second = make_user(conn, name="Admin Dois", email="dois@example.com", role="ADMIN", access_level=3)

    assert edit_user(conn, second, role="USER").role == "USER"


def test_update_with_invalid_level_keeps_previous_value(conn):
    user = make_user(conn, access_level=2)
    with pytest.raises(ValidationError):
        edit_user(conn, user, access_level=999)
    assert user_service.get_user(conn, user.id).access_level == 2


def test_update_can_keep_own_email(conn):
    user = make_user(conn, email="maria@example.com")
    assert edit_user(conn, user, name="Maria Nova").name == "Maria Nova"


def test_update_cannot_take_another_users_email(conn):
    make_user(conn, email="maria@example.com")
    other = make_user(conn, name="João", email="joao@example.com")
    with pytest.raises(ValidationError) as exc:
        edit_user(conn, other, email="maria@example.com")
    assert "email" in exc.value.errors


def test_update_missing_user_raises(conn):
    with pytest.raises(UserNotFoundError):
        user_service.update_user(conn, 999, **valid_data())


# ----------------------------------------------------------------------
# Ativação e desativação
# ----------------------------------------------------------------------

def test_deactivate_and_reactivate(conn):
    user = make_user(conn)

    assert user_service.deactivate_user(conn, user.id).active is False
    assert user_service.get_user(conn, user.id).active is False

    assert user_service.activate_user(conn, user.id).active is True


def test_deactivate_keeps_the_record(conn):
    """Revogar acesso não apaga o usuário (preserva histórico para auditoria)."""
    user = make_user(conn)
    user_service.deactivate_user(conn, user.id)
    assert user_service.get_user(conn, user.id) is not None


def test_activate_missing_user_raises(conn):
    with pytest.raises(UserNotFoundError):
        user_service.activate_user(conn, 999)


def test_cannot_deactivate_the_only_active_admin(conn):
    admin = make_user(conn, role="ADMIN", access_level=3)
    with pytest.raises(ValidationError) as exc:
        user_service.deactivate_user(conn, admin.id)
    assert "active" in exc.value.errors
    assert user_service.get_user(conn, admin.id).active is True


def test_cannot_remove_admin_role_from_the_only_active_admin(conn):
    admin = make_user(conn, role="ADMIN", access_level=3)
    with pytest.raises(ValidationError) as exc:
        edit_user(conn, admin, role="USER")
    assert "role" in exc.value.errors
    assert user_service.get_user(conn, admin.id).role == "ADMIN"


def test_can_deactivate_an_admin_when_another_active_admin_exists(conn):
    first = make_user(conn, name="Admin Um", email="um@example.com", role="ADMIN", access_level=3)
    make_user(conn, name="Admin Dois", email="dois@example.com", role="ADMIN", access_level=3)
    assert user_service.deactivate_user(conn, first.id).active is False


# ----------------------------------------------------------------------
# Consultas e administrador inicial
# ----------------------------------------------------------------------

def test_count_users(conn):
    a = make_user(conn, email="a@example.com")
    make_user(conn, name="B", email="b@example.com")
    make_user(conn, name="C", email="c@example.com")
    user_service.deactivate_user(conn, a.id)

    assert user_service.count_users(conn) == {"total": 3, "active": 2, "inactive": 1}


def test_list_users_is_alphabetical(conn):
    make_user(conn, name="Carlos", email="c@example.com")
    make_user(conn, name="ana", email="a@example.com")
    make_user(conn, name="Bruno", email="b@example.com")

    assert [u.name for u in user_service.list_users(conn)] == ["ana", "Bruno", "Carlos"]


def test_get_user_returns_none_when_missing(conn):
    assert user_service.get_user(conn, 999) is None


def test_default_admin_is_created_when_database_is_empty(conn):
    admin = user_service.ensure_default_admin(conn)

    assert admin.email == "admin@bioauth.local"
    assert admin.job_title == "Administrador do Sistema"
    assert admin.division
    assert admin.role == "ADMIN"
    assert admin.access_level == 3
    assert admin.active is True


def test_default_admin_is_not_recreated(conn):
    user_service.ensure_default_admin(conn)
    assert user_service.ensure_default_admin(conn) is None
    assert user_service.count_users(conn)["total"] == 1


def test_default_admin_is_not_created_when_users_already_exist(conn):
    make_user(conn)
    assert user_service.ensure_default_admin(conn) is None


# ----------------------------------------------------------------------
# Segunda linha de defesa: o próprio banco recusa dados inválidos
# ----------------------------------------------------------------------

@pytest.mark.parametrize("role, level", [("ADMIN", 999), ("ROOT", 1)])
def test_database_constraints_reject_invalid_values_even_without_the_service(conn, role, level):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (name, email, job_title, division, role, access_level, active, "
            "created_at, updated_at) VALUES ('X', 'x@example.com', 'C', 'D', ?, ?, 1, 'now', 'now')",
            (role, level),
        )
