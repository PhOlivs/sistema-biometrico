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
    data = {
        "name": "Maria Souza",
        "email": "maria@example.com",
        "job_title": "Analista Ambiental",
        "division": "Divisão de Recursos Hídricos",
        "role": "USER",
        "access_level": "1",
    }
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
    assert "Administração do BIOAUTH" in html   # divisão do admin inicial
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
    html = page(response)
    assert response.status_code == 400
    assert "Informe o nome completo" in html
    assert "Informe o cargo" in html
    assert "Informe a divisão" in html


def test_job_title_and_division_are_saved(client, db):
    client.post(
        "/admin/users/new",
        data=valid_form(job_title="Diretor de Recursos Naturais", division="Diretoria de Recursos Naturais"),
    )
    user = user_service.list_users(db)[-1]
    assert user.job_title == "Diretor de Recursos Naturais"
    assert user.division == "Diretoria de Recursos Naturais"


# ----------------------------------------------------------------------
# Fluxo de cadastro: 1) dados do usuário  ->  2) cadastro biométrico
# ----------------------------------------------------------------------

def test_creating_a_user_leads_to_the_biometric_step(client, db):
    response = client.post("/admin/users/new", data=valid_form())
    user = user_service.list_users(db)[-1]

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/admin/users/{user.id}/biometric")


def test_failed_registration_does_not_advance_to_biometric_step(client, db):
    response = client.post("/admin/users/new", data=valid_form(access_level="999"))
    assert response.status_code == 400
    assert "Location" not in response.headers


def test_biometric_page_shows_identity_and_camera(client, db):
    client.post(
        "/admin/users/new",
        data=valid_form(
            name="João da Silva", job_title="Diretor de Recursos Naturais",
            division="Diretoria de Recursos Naturais", access_level="2",
            email="joao@example.com",
        ),
    )
    user = user_service.list_users(db)[-1]

    response = client.get(f"/admin/users/{user.id}/biometric")
    html = page(response)

    assert response.status_code == 200
    assert "João da Silva" in html
    assert "Diretor de Recursos Naturais" in html
    assert "Diretoria de Recursos Naturais" in html
    assert "Nível 2" in html
    assert "Aguardando captura" in html
    assert 'id="camera-feed"' in html          # webcam reaproveitada
    assert "js/camera.js" in html


def test_capture_button_is_disabled_until_processing_exists(client, db):
    """Nesta fase não existe captura: o botão não pode estar ativo."""
    user = create_and_get(client, db)
    html = page(client.get(f"/admin/users/{user.id}/biometric"))

    import re
    button = re.search(r"<button[^>]*>\s*Capturar biometria", html)
    assert button is not None
    assert "disabled" in button.group(0)


def test_biometric_step_does_not_change_access_level(client, db):
    """O nível é definido no cadastro pelo administrador; a biometria não o altera."""
    user = create_and_get(client, db, access_level="2")
    client.get(f"/admin/users/{user.id}/biometric")
    assert user_service.get_user(db, user.id).access_level == 2


def test_biometric_page_for_unknown_user_is_404(client):
    assert client.get("/admin/users/999/biometric").status_code == 404


def test_biometric_page_is_read_only(client, db):
    user = create_and_get(client, db)
    assert client.post(f"/admin/users/{user.id}/biometric").status_code == 405


def test_new_user_form_shows_steps_but_edit_form_does_not(client, db):
    new_html = page(client.get("/admin/users/new"))
    assert "Etapas do cadastro" in new_html
    assert "Salvar e continuar para a biometria" in new_html

    user = create_and_get(client, db)
    edit_html = page(client.get(f"/admin/users/{user.id}/edit"))
    assert "Etapas do cadastro" not in edit_html
    assert "Salvar alterações" in edit_html


def test_users_table_links_to_the_biometric_page(client, db):
    user = create_and_get(client, db)
    assert f"/admin/users/{user.id}/biometric" in page(client.get("/admin/users"))


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


def test_edit_changes_job_title_and_division(client, db):
    user = create_and_get(client, db)
    response = client.post(
        f"/admin/users/{user.id}/edit",
        data=valid_form(job_title="Diretora", division="Diretoria de Águas"),
    )
    assert response.status_code == 302
    updated = user_service.get_user(db, user.id)
    assert (updated.job_title, updated.division) == ("Diretora", "Diretoria de Águas")


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
