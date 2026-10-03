import json
import base64
import re

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from database import database
from services import auth_service, user_service


@pytest.fixture
def setup_app(tmp_path):
    path = str(tmp_path / "test.db")
    app = create_app({
        "TESTING": True, "DATABASE_PATH": path, "SECRET_KEY": "test-secret",
        "DATA_ENCRYPTION_KEY": None, "DEBUG": True,
    })
    return app, path


def csrf(html: str) -> str:
    return re.search(r'<meta name="csrf-token" content="([^"]+)"', html).group(1)


def create_admin(path):
    conn = database.connect(path)
    admin = user_service.create_provisioned_admin(
        conn, name="Administradora", email="admin@egíde.com.br",
        password_hash=generate_password_hash("SenhaAdmin-123!", method="scrypt"),
    )
    conn.executemany(
        "INSERT INTO biometric_profiles (user_id, angle, embedding, model_version, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (admin.id, angle, b"protected", "test", "2026-09-28T12:00:00+00:00")
            for angle in ("FRONT", "RIGHT", "LEFT")
        ],
    )
    conn.commit()
    conn.close()
    return admin


def sign_in_admin(client, path, monkeypatch):
    create_admin(path)
    import routes.auth

    monkeypatch.setattr(
        routes.auth.biometric_service, "verify_user",
        lambda *args, **kwargs: (
            True,
            {"FRONT": .9, "RIGHT": .8, "LEFT": .7, "MAX": .9, "THRESHOLD": .363},
        ),
    )
    login_page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": csrf(login_page.get_data(as_text=True)),
            "matricula": "Z001",
            "password": "SenhaAdmin-123!",
        },
    )
    assert response.status_code == 302
    auth_page = client.get("/autenticacao")
    auth_html = auth_page.get_data(as_text=True)
    challenge_match = re.search(r"data-challenge='([^']+)'", auth_html)
    assert challenge_match
    challenge = json.loads(challenge_match.group(1))
    response = client.post(
        "/api/auth/face",
        json={"image": "test", "liveness_images": ["turn"] * len(challenge)},
        headers={"X-CSRFToken": csrf(auth_page.get_data(as_text=True))},
    )
    assert response.status_code == 200
    assert response.json["redirect"] == "/admin/"
    conn = database.connect(path)
    details = json.loads(conn.execute(
        "SELECT details FROM access_logs WHERE event = 'BIOMETRIC_AUTHENTICATION' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()["details"])
    assert details["liveness"] == "passed"
    assert details["face_scores"]["front"] == .9
    assert details["face_scores"]["right"] == .8
    assert details["face_scores"]["left"] == .7
    assert details["face_scores"]["max"] == .9
    assert details["face_scores"]["threshold"] == .363
    conn.close()


def test_home_and_login_render(setup_app):
    app, _ = setup_app
    client = app.test_client()
    assert client.get("/").status_code == 200
    login = client.get("/login")
    assert login.status_code == 200
    assert "data-password-toggle" in login.get_data(as_text=True)
    register = client.get("/cadastro")
    assert register.status_code == 200
    registration_html = register.get_data(as_text=True)
    assert "Senha fraca" in registration_html
    assert "Mínimo de caracteres: 12" in registration_html
    assert "Letras e números" in registration_html
    assert "Uma letra maiúscula" in registration_html
    assert "Um símbolo" in registration_html
    assert "Protótipo acadêmico" in client.get("/").get_data(as_text=True)


def test_admin_pages_are_not_public(setup_app):
    app, _ = setup_app
    client = app.test_client()
    for url in ("/admin/", "/admin/usuarios", "/admin/solicitacoes", "/admin/acessos"):
        response = client.get(url)
        assert response.status_code == 302
        assert response.location.endswith("/login")


def test_admin_delegation_ui_has_controlled_position_picker(setup_app, monkeypatch):
    app, path = setup_app
    client = app.test_client()
    sign_in_admin(client, path, monkeypatch)
    page = client.get("/admin/usuarios/1/editar")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Delegação Institucional" in html
    assert "Selecionar cargo" in html
    assert "NÍVEL 1" in html
    assert "NÍVEL 2" in html
    assert "NÍVEL 3" in html
    assert "GESTÃO" in html
    assert 'name="access_level"' not in html
    assert 'name="position_code"' in html


def test_unapproved_user_cannot_open_authenticated_area(setup_app):
    app, path = setup_app
    conn = database.connect(path)
    pending = user_service.create_pending_user(
        conn,         name="Pessoa Pendente", birth_date="1990-01-01",
        cpf_encrypted="encrypted", cpf_digest="unique-digest", rg_encrypted=None,
        email="pending@egíde.com.br", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaPendente-123!", method="scrypt"),
        biometric_consent=True,
    )
    conn.close()
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = pending.id
    assert client.get("/painel").status_code == 302


def test_login_rejects_pending_user_and_logs_attempt(setup_app):
    app, path = setup_app
    conn = database.connect(path)
    user_service.create_pending_user(
        conn,         name="Pessoa Pendente", birth_date="1990-01-01",
        cpf_encrypted="encrypted", cpf_digest="unique-digest", rg_encrypted=None,
        email="pending@egíde.com.br", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaPendente-123!", method="scrypt"),
        biometric_consent=True,
    )
    conn.execute(
        "UPDATE users SET matricula = 'X001' WHERE email = 'pending@egíde.com.br'"
    )
    conn.commit()
    conn.close()
    client = app.test_client()
    login_page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": csrf(login_page.get_data(as_text=True)),
            "matricula": "X001", "password": "SenhaPendente-123!",
        },
    )
    assert response.status_code == 401
    assert "aguarda aprovação" in response.get_data(as_text=True)
    conn = database.connect(path)
    assert conn.execute("SELECT result FROM access_logs").fetchone()["result"] == "DENIED"
    conn.close()


def test_registration_validates_server_and_starts_pending_flow(setup_app):
    app, path = setup_app
    client = app.test_client()
    page = client.get("/cadastro")
    registration_html = page.get_data(as_text=True)
    assert 'name="job_title"' not in registration_html
    assert 'name="division"' not in registration_html
    assert 'name="position_code"' not in registration_html
    assert 'name="access_level"' not in registration_html
    token = csrf(page.get_data(as_text=True))
    data = {
        "csrf_token": token, "name": "Pessoa Nova", "birth_date": "1990-01-01",
        "cpf": "529.982.247-25", "rg": "", "job_title": "Analista",
        "division": "Divisão X", "email": "nova@egíde.com.br",
        "password": "UmaSenhaForte-123!", "password_confirmation": "UmaSenhaForte-123!",
        "biometric_consent": "yes",
    }
    response = client.post("/cadastro", data=data)
    assert response.status_code == 302, response.get_data(as_text=True)
    assert response.status_code == 302
    assert response.location.endswith("/cadastro/biometria")
    conn = database.connect(path)
    row = conn.execute("SELECT * FROM users WHERE email = 'nova@egíde.com.br'").fetchone()
    assert row["matricula"] is None
    assert row["access_level_assigned"] == 0
    assert row["status"] == "PENDING"
    assert row["access_level"] == 1
    assert row["job_title"] == "A definir"
    assert row["division"] == "A definir"
    assert row["password_hash"] != data["password"]
    assert row["cpf_encrypted"] != "52998224725"
    conn.close()


def test_csrf_protects_mutating_requests(setup_app):
    app, _ = setup_app
    client = app.test_client()
    assert client.post("/login", data={"matricula": "X001", "password": "x"}).status_code == 400


def test_admin_dashboard_and_access_logs_require_admin(setup_app, monkeypatch):
    app, path = setup_app
    client = app.test_client()
    sign_in_admin(client, path, monkeypatch)
    dashboard = client.get("/admin/")
    assert dashboard.status_code == 200
    assert "Painel administrativo" in dashboard.get_data(as_text=True)
    users = client.get("/admin/usuarios")
    assert users.status_code == 200
    chart = client.get("/admin/usuarios?view=chart")
    assert chart.status_code == 200
    assert "Organograma Institucional" in chart.get_data(as_text=True)
    edit = client.get("/admin/usuarios/1/editar")
    assert edit.status_code == 200
    assert "Delegação Institucional" in edit.get_data(as_text=True)
    edit_html = edit.get_data(as_text=True)
    assert "NÍVEL 1" in edit_html
    assert "NÍVEL 2" in edit_html
    assert "NÍVEL 3" in edit_html
    assert "GESTÃO" in edit_html
    assert 'name="access_level"' not in edit_html
    assert "Chefe de Estado-Maior" in edit.get_data(as_text=True)
    logs = client.get("/admin/acessos?result=SUCCESS")
    assert logs.status_code == 200
    assert "LOGIN_PASSWORD" in logs.get_data(as_text=True)


def test_admin_approval_route_requires_csrf_and_biometric(setup_app, monkeypatch):
    app, path = setup_app
    client = app.test_client()
    sign_in_admin(client, path, monkeypatch)
    conn = database.connect(path)
    pending = user_service.create_pending_user(
        conn, name="Pessoa Pendente", birth_date="1990-01-01",
        cpf_encrypted=None, cpf_digest="approval-digest", rg_encrypted=None,
        email="approval@egíde.com.br", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaPendente-123!", method="scrypt"),
        biometric_consent=True,
    )
    conn.executemany(
        "INSERT INTO biometric_profiles (user_id, angle, embedding, model_version, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (pending.id, angle, b"protected", "test", "2026-09-28T12:00:00+00:00")
            for angle in ("FRONT", "RIGHT", "LEFT")
        ],
    )
    conn.execute(
        "UPDATE users SET profile_photo_encrypted = ? WHERE id = ?",
        (b"protected-photo", pending.id),
    )
    admin_assignment = conn.execute(
        "SELECT area.id AS area_id, team.id AS team_id "
        "FROM organization_areas area JOIN organization_teams team ON team.area_id = area.id "
        "WHERE area.code = 'ADMINISTRATION' AND team.code = 'ADMIN_RESOURCES'"
    ).fetchone()
    conn.commit()
    conn.close()
    detail = client.get(f"/admin/solicitacoes/{pending.id}")
    assert "Delegação Institucional" in detail.get_data(as_text=True)
    token = csrf(detail.get_data(as_text=True))
    response = client.post(
        f"/admin/solicitacoes/{pending.id}/aprovar",
        data={
            "csrf_token": token,
            "position_code": "EXECUTIVE_DIRECTOR",
            "area_id": str(admin_assignment["area_id"]),
            "team_id": str(admin_assignment["team_id"]),
            "manager_user_id": "1",
        },
    )
    assert response.status_code == 302
    conn = database.connect(path)
    approved = user_service.get_user(conn, pending.id)
    assert approved.status == "APPROVED"
    assert approved.access_level == 3
    assert approved.matricula == "Z002"
    assert approved.position_code == "EXECUTIVE_DIRECTOR"
    assert approved.manager_user_id == 1
    conn.close()


def test_profile_photo_is_decrypted_only_in_admin_area(setup_app, monkeypatch):
    app, path = setup_app
    client = app.test_client()
    sign_in_admin(client, path, monkeypatch)
    jpeg = b"\xff\xd8\xff\xe0test-image\xff\xd9"
    conn = database.connect(path)
    pending = user_service.create_pending_user(
        conn, name="Pessoa com Foto", birth_date="1990-01-01",
        cpf_encrypted=None, cpf_digest="photo-digest", rg_encrypted=None,
        email="photo@egíde.com.br", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaPendente-123!", method="scrypt"),
        biometric_consent=True,
    )
    with app.app_context():
        encrypted_photo = auth_service.encrypt_sensitive(base64.b64encode(jpeg).decode("ascii"))
    conn.execute(
        "UPDATE users SET profile_photo_encrypted = ? WHERE id = ?",
        (encrypted_photo.encode("ascii"), pending.id),
    )
    conn.commit()
    conn.close()

    response = client.get(f"/admin/usuarios/{pending.id}/foto")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.data == jpeg
    assert response.headers["Cache-Control"] == "private, no-store"

    public_client = app.test_client()
    assert public_client.get(f"/admin/usuarios/{pending.id}/foto").status_code == 302


def test_toxin_access_is_server_enforced_and_audited(setup_app):
    app, path = setup_app
    conn = database.connect(path)
    user = user_service.create_pending_user(
        conn, name="Pessoa Aprovada", birth_date="1990-01-01",
        cpf_encrypted="encrypted", cpf_digest="level-digest", rg_encrypted=None,
        email="level@egíde.com.br", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaAprovada-123!", method="scrypt"),
        biometric_consent=True,
    )
    conn.execute(
        "UPDATE users SET status = 'APPROVED', matricula = 'X001', access_level_assigned = 1 "
        "WHERE id = ?", (user.id,)
    )
    conn.commit()
    toxin = conn.execute("SELECT id FROM toxins WHERE access_level = 3 LIMIT 1").fetchone()
    conn.close()
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user.id
    response = client.get(f"/toxinas/{toxin['id']}")
    assert response.status_code == 403
    assert "Acesso negado" in response.get_data(as_text=True)
    conn = database.connect(path)
    event = conn.execute(
        "SELECT event, result FROM access_logs WHERE resource_id = ?", (toxin["id"],)
    ).fetchone()
    assert (event["event"], event["result"]) == ("SUPERIOR_LEVEL_ATTEMPT", "DENIED")
    conn.close()


def test_regular_user_cannot_access_admin_routes(setup_app):
    app, path = setup_app
    conn = database.connect(path)
    user = user_service.create_pending_user(
        conn, name="Pessoa Aprovada", birth_date="1990-01-01",
        cpf_encrypted="encrypted", cpf_digest="regular-digest", rg_encrypted=None,
        email="regular@egíde.com.br", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaAprovada-123!", method="scrypt"),
        biometric_consent=True,
    )
    conn.execute(
        "UPDATE users SET status = 'APPROVED', matricula = 'X001', access_level_assigned = 1 "
        "WHERE id = ?", (user.id,)
    )
    conn.commit()
    conn.close()
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user.id
    assert client.get("/admin/").status_code == 403
