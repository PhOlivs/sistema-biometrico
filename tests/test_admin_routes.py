import re

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from database import database
from services import user_service


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
        conn, name="Administradora", email="admin@example.com",
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

    monkeypatch.setattr(routes.auth.biometric_service, "verify_user", lambda *args, **kwargs: (True, .9))
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
    response = client.post(
        "/api/auth/face",
        json={"image": "test"},
        headers={"X-CSRFToken": csrf(auth_page.get_data(as_text=True))},
    )
    assert response.status_code == 200
    assert response.json["redirect"] == "/admin/"


def test_home_and_login_render(setup_app):
    app, _ = setup_app
    client = app.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/login").status_code == 200
    assert "Protótipo acadêmico" in client.get("/").get_data(as_text=True)


def test_admin_pages_are_not_public(setup_app):
    app, _ = setup_app
    client = app.test_client()
    for url in ("/admin/", "/admin/usuarios", "/admin/solicitacoes", "/admin/acessos"):
        response = client.get(url)
        assert response.status_code == 302
        assert response.location.endswith("/login")


def test_unapproved_user_cannot_open_authenticated_area(setup_app):
    app, path = setup_app
    conn = database.connect(path)
    pending = user_service.create_pending_user(
        conn, name="Pessoa Pendente", birth_date="1990-01-01",
        cpf_encrypted="encrypted", cpf_digest="unique-digest", rg_encrypted=None,
        email="pending@example.com", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaPendente-123!", method="scrypt"),
        access_level=1,
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
        conn, name="Pessoa Pendente", birth_date="1990-01-01",
        cpf_encrypted="encrypted", cpf_digest="unique-digest", rg_encrypted=None,
        email="pending@example.com", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaPendente-123!", method="scrypt"),
        access_level=1,
    )
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
    token = csrf(page.get_data(as_text=True))
    data = {
        "csrf_token": token, "name": "Pessoa Nova", "birth_date": "1990-01-01",
        "cpf": "529.982.247-25", "rg": "", "job_title": "Analista",
        "division": "Divisão X", "email": "nova@example.com", "access_level": "2",
        "password": "UmaSenhaForte-123!", "password_confirmation": "UmaSenhaForte-123!",
    }
    response = client.post("/cadastro", data=data)
    assert response.status_code == 302
    assert response.location.endswith("/cadastro/biometria")
    conn = database.connect(path)
    row = conn.execute("SELECT * FROM users WHERE email = 'nova@example.com'").fetchone()
    assert row["matricula"] == "Y001"
    assert row["status"] == "PENDING"
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
        email="approval@example.com", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaPendente-123!", method="scrypt"),
        access_level=1,
    )
    conn.close()
    detail = client.get(f"/admin/solicitacoes/{pending.id}")
    token = csrf(detail.get_data(as_text=True))
    response = client.post(
        f"/admin/solicitacoes/{pending.id}/aprovar",
        data={"csrf_token": token},
    )
    assert response.status_code == 302
    conn = database.connect(path)
    assert user_service.get_user(conn, pending.id).status == "PENDING"
    conn.close()


def test_toxin_access_is_server_enforced_and_audited(setup_app):
    app, path = setup_app
    conn = database.connect(path)
    user = user_service.create_pending_user(
        conn, name="Pessoa Aprovada", birth_date="1990-01-01",
        cpf_encrypted="encrypted", cpf_digest="level-digest", rg_encrypted=None,
        email="level@example.com", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaAprovada-123!", method="scrypt"),
        access_level=1,
    )
    conn.execute("UPDATE users SET status = 'APPROVED' WHERE id = ?", (user.id,))
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
        email="regular@example.com", job_title="Analista", division="Divisão",
        password_hash=generate_password_hash("SenhaAprovada-123!", method="scrypt"),
        access_level=1,
    )
    conn.execute("UPDATE users SET status = 'APPROVED' WHERE id = ?", (user.id,))
    conn.commit()
    conn.close()
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user.id
    assert client.get("/admin/").status_code == 403
