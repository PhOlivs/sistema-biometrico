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
        "email": "pessoa@egíde.com.br",
        "job_title": "Analista",
        "division": "Divisão Acadêmica",
        "password": "SenhaSegura-123!",
        "password_confirmation": "SenhaSegura-123!",
        "biometric_consent": "yes",
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
        assert user.matricula is None
        assert user.access_level is None
        assert user.biometric_photo_consent_at
        assert user.job_title == "A definir"
        assert user.division == "A definir"


def test_public_registration_cannot_assign_organizational_fields(app_and_db):
    app, conn = app_and_db
    with app.app_context():
        user = auth_service.register_user(
            conn,
            registration_data(job_title="Diretor Executivo", division="Tecnologia"),
        )
        assert user.job_title == "A definir"
        assert user.division == "A definir"


@pytest.mark.parametrize(
    "cpf,expected",
    [
        ("12345678901", "12345678901"),
        ("111.111.111-11", "11111111111"),
        ("12.345 67-8901", "12345678901"),
        ("12-345.678 901", "12345678901"),
    ],
)
def test_registration_accepts_eleven_cpf_digits_with_any_format(app_and_db, cpf, expected):
    app, conn = app_and_db
    with app.app_context():
        user = auth_service.register_user(conn, registration_data(cpf=cpf))
        assert auth_service.decrypt_sensitive(user.cpf_encrypted) == expected


@pytest.mark.parametrize(
    "password,missing",
    [
        ("Abcdefghijk!", "letras e números"),
        ("Abcdefghijk1", "um símbolo"),
        ("abcdefghijkl1!", "uma letra maiúscula"),
    ],
)
def test_registration_rejects_passwords_missing_strength_requirements(app_and_db, password, missing):
    app, conn = app_and_db
    with app.app_context(), pytest.raises(ValidationError) as error:
        auth_service.register_user(
            conn,
            registration_data(password=password, password_confirmation=password),
        )
    assert missing in error.value.errors["password"]


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"cpf": "123-45"}, "cpf"),
        ({"birth_date": "not-a-date"}, "birth_date"),
        ({"password": "short"}, "password"),
        ({"password_confirmation": "OutraSenha-123!"}, "password_confirmation"),
        ({"biometric_consent": ""}, "biometric_consent"),
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
            auth_service.register_user(conn, registration_data(email="other@egíde.com.br"))
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


def test_public_registration_requires_institutional_email(app_and_db):
    app, conn = app_and_db
    with app.app_context(), pytest.raises(ValidationError) as error:
        auth_service.register_user(
            conn, registration_data(email="pessoa@example.com")
        )
    assert "egíde.com.br" in error.value.errors["email"]
