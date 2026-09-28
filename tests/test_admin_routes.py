"""
Testes das rotas /admin usando o cliente de teste do Flask.

Cada teste cria uma aplicação com banco temporário. Os testes enviam
requisições POST diretamente (sem formulário HTML), como um cliente mal
intencionado faria, para provar que a validação do backend funciona.
"""

import pytest

from app import create_app
from database import database
from services import user_service


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def client(db_path):
    app = create_app({"TESTING": True, "DATABASE_PATH": db_path, "SECRET_KEY": "test"})
    return app.test_client()


@pytest.fixture
def db(db_path, client):  # depende de `client` para o banco já existir
    connection = database.connect(db_path)
    yield connection
    connection.close()


def valid_form(**overrides):
    data = {"name": "Maria Souza", "email": "maria@example.com", "role": "USER", "access_level": "1"}
    data.update(overrides)
    return data


def page(response):
    return response.get_data(as_text=True)


# ----------------------------------------------------------------------
# Banco e páginas
# ----------------------------------------------------------------------

def test_database_file_is_created_with_default_admin(client, db_path, db):
    import os

    assert os.path.exists(db_path)
    users = user_service.list_users(db)
    assert [u.email for u in users] == ["admin@bioauth.local"]


def test_existing_pages_still_work(client):
    assert client.get("/").status_code == 200
    assert client.get("/autenticacao").status_code == 200


@pytest.mark.parametrize("url", ["/admin", "/admin/users", "/admin/users/new"])
def test_admin_pages_render(client, url):
    response = client.get(url)
    assert response.status_code == 200
    assert "Painel sem proteção de acesso" in page(response)


def test_dashboard_shows_default_admin_and_totals(client):
    html = page(client.get("/admin"))
    assert "Administrador do Sistema" in html
    assert "admin@bioauth.local" in html
    assert "Administrador" in html


def test_admin_is_not_shown_as_a_fourth_level(client):
    html = page(client.get("/admin/users"))
    assert "Nível 4" not in html
    assert "Nível 3" in html


# ----------------------------------------------------------------------
# Cadastro
# ----------------------------------------------------------------------

@pytest.mark.parametrize("level", ["1", "2", "3"])
def test_create_user_for_each_level(client, db, level):
    response = client.post(
        "/admin/users/new",
        data=valid_form(email=f"n{level}@example.com", access_level=level),
    )
    assert response.status_code == 302

    created = [u for u in user_service.list_users(db) if u.email == f"n{level}@example.com"]
    assert created[0].access_level == int(level)


def test_invalid_level_sent_directly_is_rejected_by_backend(client, db):
    response = client.post("/admin/users/new", data=valid_form(access_level="999"))

    assert response.status_code == 400
    assert "Nível de acesso inválido" in page(response)
    assert user_service.count_users(db)["total"] == 1  # só o admin inicial


def test_invalid_role_sent_directly_is_rejected_by_backend(client, db):
    response = client.post("/admin/users/new", data=valid_form(role="SUPERADMIN"))
    assert response.status_code == 400
    assert user_service.count_users(db)["total"] == 1


def test_admin_with_level_999_is_rejected(client, db):
    response = client.post("/admin/users/new", data=valid_form(role="ADMIN", access_level="999"))
    assert response.status_code == 400
    assert user_service.count_users(db)["total"] == 1


def test_duplicate_email_shows_error_and_keeps_typed_values(client, db):
    client.post("/admin/users/new", data=valid_form())
    response = client.post("/admin/users/new", data=valid_form(name="Outra Pessoa"))

    html = page(response)
    assert response.status_code == 400
    assert "Já existe um usuário com este e-mail" in html
    assert "Outra Pessoa" in html  # o formulário preserva o que foi digitado
    assert user_service.count_users(db)["total"] == 2


def test_missing_fields_are_rejected(client):
    response = client.post("/admin/users/new", data={})
    assert response.status_code == 400
    assert "Informe o nome completo" in page(response)


# ----------------------------------------------------------------------
# Edição, ativação e desativação
# ----------------------------------------------------------------------

def create_and_get(client, db, **overrides):
    client.post("/admin/users/new", data=valid_form(**overrides))
    return [u for u in user_service.list_users(db) if u.email == valid_form(**overrides)["email"]][0]


def test_edit_form_shows_current_values(client, db):
    user = create_and_get(client, db)
    html = page(client.get(f"/admin/users/{user.id}/edit"))
    assert "Maria Souza" in html
    assert "maria@example.com" in html


def test_edit_changes_level(client, db):
    user = create_and_get(client, db)
    response = client.post(
        f"/admin/users/{user.id}/edit", data=valid_form(access_level="3")
    )
    assert response.status_code == 302
    assert user_service.get_user(db, user.id).access_level == 3


def test_edit_with_invalid_level_is_rejected(client, db):
    user = create_and_get(client, db)
    response = client.post(
        f"/admin/users/{user.id}/edit", data=valid_form(access_level="42")
    )
    assert response.status_code == 400
    assert user_service.get_user(db, user.id).access_level == 1


def test_deactivate_and_reactivate(client, db):
    user = create_and_get(client, db)

    client.post(f"/admin/users/{user.id}/deactivate")
    assert user_service.get_user(db, user.id).active is False

    client.post(f"/admin/users/{user.id}/activate")
    assert user_service.get_user(db, user.id).active is True


def test_cannot_deactivate_the_only_admin_and_user_is_told_why(client, db):
    admin = user_service.list_users(db)[0]

    response = client.post(f"/admin/users/{admin.id}/deactivate", follow_redirects=True)

    assert "único administrador ativo" in page(response)
    assert user_service.get_user(db, admin.id).active is True


def test_unknown_user_returns_404(client):
    assert client.get("/admin/users/999/edit").status_code == 404
    assert client.post("/admin/users/999/deactivate").status_code == 404
    assert client.post("/admin/users/999/activate").status_code == 404


def test_state_changing_routes_do_not_accept_get(client, db):
    user = create_and_get(client, db)
    assert client.get(f"/admin/users/{user.id}/deactivate").status_code == 405
    assert client.get(f"/admin/users/{user.id}/activate").status_code == 405
