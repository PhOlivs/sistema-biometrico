"""Credential checks, enrollment validation and privacy-sensitive fields."""

import base64
import hashlib
import hmac
import re
from datetime import date

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from models.user import STATUS_APPROVED
from services import audit_service, user_service

_CPF_DIGITS = re.compile(r"\D")


def _cipher() -> Fernet:
    configured = current_app.config.get("DATA_ENCRYPTION_KEY")
    if configured:
        key = configured.encode("ascii") if isinstance(configured, str) else configured
    else:
        secret = current_app.config["SECRET_KEY"].encode("utf-8")
        digest = hashlib.sha256(b"egide-local-pii-v1:" + secret).digest()
        key = base64.urlsafe_b64encode(digest)
    try:
        return Fernet(key)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("EGIDE_DATA_ENCRYPTION_KEY deve ser uma chave Fernet válida.") from exc


def _digest_key() -> bytes:
    configured = current_app.config.get("DATA_ENCRYPTION_KEY")
    if configured:
        encoded = configured.encode("ascii") if isinstance(configured, str) else configured
        try:
            return hashlib.sha256(b"egide-cpf-index-v1:" + base64.urlsafe_b64decode(encoded)).digest()
        except (ValueError, TypeError) as exc:
            raise RuntimeError("EGIDE_DATA_ENCRYPTION_KEY deve ser uma chave Fernet válida.") from exc
    return hashlib.sha256(
        b"egide-cpf-index-v1:" + current_app.config["SECRET_KEY"].encode("utf-8")
    ).digest()


def cpf_digest(cpf: str | None) -> str | None:
    if not cpf:
        return None
    return hmac.new(_digest_key(), cpf.encode("ascii"), hashlib.sha256).hexdigest()


def normalize_cpf(raw: str) -> str:
    if not re.fullmatch(r"[0-9.\-\s]*", raw or ""):
        raise ValueError("Use apenas números, pontos ou hífen no CPF.")
    digits = re.sub(r"[^0-9]", "", raw or "")
    if len(digits) != 11:
        raise ValueError("Informe os 11 dígitos do CPF.")
    return digits


def _password_requirements(password: str) -> list[str]:
    requirements = []
    if len(password) < 12:
        requirements.append("mínimo de 12 caracteres")
    if not (any(char.isalpha() for char in password) and any(char.isdigit() for char in password)):
        requirements.append("letras e números")
    if not any(char.isupper() for char in password):
        requirements.append("uma letra maiúscula")
    if not any(not char.isalnum() and not char.isspace() for char in password):
        requirements.append("um símbolo")
    return requirements


def encrypt_sensitive(value: str | None) -> str | None:
    if not value:
        return None
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_sensitive(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Não foi possível descriptografar o dado cadastral; verifique a chave.") from exc


def validate_birth_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Informe uma data de nascimento válida.") from exc
    if parsed > date.today():
        raise ValueError("A data de nascimento não pode estar no futuro.")
    return parsed.isoformat()


def register_user(conn, data: dict):
    errors = {}
    if data.get("biometric_consent") not in ("yes", "on", "true"):
        errors["biometric_consent"] = "Confirme o consentimento para o registro e armazenamento da biometria."
    try:
        cpf = normalize_cpf(data.get("cpf", ""))
    except ValueError as exc:
        errors["cpf"] = str(exc)
        cpf = None
    try:
        birth_date = validate_birth_date(data.get("birth_date", ""))
    except ValueError as exc:
        errors["birth_date"] = str(exc)
        birth_date = None
    password = data.get("password")
    if not isinstance(password, str):
        password = ""
    confirmation = data.get("password_confirmation")
    if not isinstance(confirmation, str):
        confirmation = ""
    rg = data.get("rg") or ""
    if not isinstance(rg, str):
        rg = ""
        errors["rg"] = "Informe um RG válido."
    if len(password) > 128:
        errors["password"] = "A senha deve ter no máximo 128 caracteres."
    else:
        missing_requirements = _password_requirements(password)
        if missing_requirements:
            errors["password"] = (
                "A senha não atende aos requisitos: " + ", ".join(missing_requirements) + "."
            )
    if password != confirmation:
        errors["password_confirmation"] = "A confirmação de senha não confere."
    if len(rg) > 32:
        errors["rg"] = "O RG deve ter no máximo 32 caracteres."
    if errors:
        raise user_service.ValidationError(errors)

    return user_service.create_pending_user(
        conn,
        name=data.get("name"),
        birth_date=birth_date,
        cpf_encrypted=encrypt_sensitive(cpf),
        cpf_digest=cpf_digest(cpf),
        rg_encrypted=encrypt_sensitive(rg.strip() or None),
        email=data.get("email"),
        job_title=data.get("job_title"),
        division=data.get("division"),
        password_hash=generate_password_hash(password, method="scrypt"),
        biometric_consent=True,
    )


def verify_password(conn, *, matricula: str, password: str):
    user = user_service.get_user_by_matricula(conn, matricula)
    row = conn.execute(
        "SELECT password_hash, status FROM users WHERE matricula = ? AND deleted_at IS NULL",
        ((matricula or "").strip().upper(),),
    ).fetchone()
    if user is None or row is None or not row["password_hash"] or not check_password_hash(
        row["password_hash"], password or ""
    ):
        audit_service.record_access(
            conn, event="LOGIN", result="FAILURE",
            user_id=user.id if user else None,
            matricula=(matricula or "").strip().upper()[:20],
            auth_type="PASSWORD",
        )
        conn.commit()
        return None, "Matrícula ou senha inválida."

    if row["status"] != STATUS_APPROVED:
        event = "LOGIN_BLOCKED_STATUS"
        audit_service.record_access(
            conn, event=event, result="DENIED", user_id=user.id,
            matricula=user.matricula, auth_type="PASSWORD",
            details={"status": row["status"]},
        )
        conn.commit()
        return None, {
            "PENDING": "Seu cadastro aguarda aprovação administrativa.",
            "REJECTED": "O cadastro não foi aprovado. Entre em contato com a administração.",
            "SUSPENDED": "O acesso está suspenso. Entre em contato com a administração.",
            "INACTIVE": "Este cadastro foi desativado.",
        }.get(row["status"], "Acesso não autorizado.")

    audit_service.record_access(
        conn, event="LOGIN_PASSWORD", result="SUCCESS", user_id=user.id,
        matricula=user.matricula, auth_type="PASSWORD",
    )
    conn.commit()
    return user, None


def mark_login_complete(conn, user_id: int) -> None:
    user = user_service.get_user(conn, user_id)
    if user is None or user.status != STATUS_APPROVED:
        return
    conn.execute(
        "UPDATE users SET last_activity_at = ?, updated_at = ? WHERE id = ?",
        (user_service.now_iso(), user_service.now_iso(), user_id),
    )
    audit_service.record_access(
        conn, event="LOGIN", result="SUCCESS", user_id=user.id,
        matricula=user.matricula, auth_type="PASSWORD+FACE",
    )
    conn.commit()
