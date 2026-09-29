import pytest

from app import create_app
from database import database
from services import auth_service, biometric_service, user_service
from services.user_service import ValidationError


@pytest.fixture
def app_and_db(tmp_path):
    path = str(tmp_path / "auth.db")
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "unit-test-secret",
        "DATABASE_PATH": path,
        "YUNET_MODEL_PATH": str(tmp_path / "missing-yunet.onnx"),
        "SFACE_MODEL_PATH": str(tmp_path / "missing-sface.onnx"),
    })
    conn = database.connect(path)
    yield app, conn
    conn.close()


def registration_data(**overrides):
    data = {
        "name": "Pessoa de Teste",
        "birth_date": "1990-01-01",
        "cpf": "529.982.247-25",
        "rg": "",
        "email": "pessoa@example.com",
        "job_title": "Analista",
        "division": "Divisão Acadêmica",
        "password": "SenhaSegura-123!",
        "password_confirmation": "SenhaSegura-123!",
        "access_level": "1",
    }
    data.update(overrides)
    return data


def test_password_hash_and_pii_encryption_round_trip(app_and_db):
    app, conn = app_and_db
    with app.app_context():
        user = auth_service.register_user(conn, registration_data())
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user.id,)).fetchone()
        assert row["password_hash"] != "SenhaSegura-123!"
        assert auth_service.decrypt_sensitive(user.cpf_encrypted) == "52998224725"
        assert user.matricula == "X001"


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"cpf": "111.111.111-11"}, "cpf"),
        ({"birth_date": "not-a-date"}, "birth_date"),
        ({"password": "short"}, "password"),
        ({"password_confirmation": "OutraSenha-123!"}, "password_confirmation"),
    ],
)
def test_registration_rejects_invalid_input(app_and_db, overrides, field):
    app, conn = app_and_db
    with app.app_context(), pytest.raises(ValidationError) as error:
        auth_service.register_user(conn, registration_data(**overrides))
    assert field in error.value.errors
    assert user_service.count_users(conn)["total"] == 0


def test_duplicate_cpf_and_email_are_rejected(app_and_db):
    app, conn = app_and_db
    with app.app_context():
        auth_service.register_user(conn, registration_data())
        with pytest.raises(ValidationError) as cpf_error:
            auth_service.register_user(conn, registration_data(email="other@example.com"))
        assert "cpf" in cpf_error.value.errors
        with pytest.raises(ValidationError) as email_error:
            auth_service.register_user(
                conn, registration_data(cpf="111.444.777-35")
            )
        assert "email" in email_error.value.errors


def test_biometric_enrollment_fails_closed_when_models_are_missing(app_and_db):
    app, conn = app_and_db
    with app.app_context(), pytest.raises(RuntimeError, match="Modelos biométricos ausentes"):
        biometric_service.enroll_user(
            conn, user_id=1,
            frames={"FRONT": "x", "RIGHT": "x", "LEFT": "x"},
            config=app.config,
        )
