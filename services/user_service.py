"""User lifecycle and administrative operations."""

import re
import sqlite3
from datetime import datetime, timezone

from models.access_level import is_valid_level
from models.user import (
    ROLE_ADMIN,
    ROLE_USER,
    STATUS_APPROVED,
    STATUS_INACTIVE,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_SUSPENDED,
    User,
)
from services import audit_service

MAX_NAME_LENGTH = 120
MAX_JOB_TITLE_LENGTH = 120
MAX_DIVISION_LENGTH = 120
MAX_EMAIL_LENGTH = 254
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MATRICULA_PREFIXES = {1: "X", 2: "Y", 3: "Z"}


class ValidationError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__("; ".join(errors.values()))


class UserNotFoundError(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_profile(*, name, email, job_title, division, access_level) -> dict:
    errors = {}
    name = (name or "").strip()
    email = (email or "").strip().lower()
    job_title = (job_title or "").strip()
    division = (division or "").strip()
    if isinstance(access_level, bool):
        level = None
    elif isinstance(access_level, int):
        level = access_level
    elif isinstance(access_level, str) and re.fullmatch(r"[0-9]+", access_level.strip()):
        level = int(access_level.strip())
    else:
        level = None

    if not name:
        errors["name"] = "Informe o nome completo."
    elif len(name) > MAX_NAME_LENGTH:
        errors["name"] = f"O nome deve ter no máximo {MAX_NAME_LENGTH} caracteres."
    if not email:
        errors["email"] = "Informe o e-mail."
    elif len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.fullmatch(email):
        errors["email"] = "Informe um e-mail válido."
    if not job_title:
        errors["job_title"] = "Informe o cargo."
    elif len(job_title) > MAX_JOB_TITLE_LENGTH:
        errors["job_title"] = f"O cargo deve ter no máximo {MAX_JOB_TITLE_LENGTH} caracteres."
    if not division:
        errors["division"] = "Informe a divisão."
    elif len(division) > MAX_DIVISION_LENGTH:
        errors["division"] = f"A divisão deve ter no máximo {MAX_DIVISION_LENGTH} caracteres."
    if not is_valid_level(level):
        errors["access_level"] = "Nível de acesso inválido. Use 1, 2 ou 3."
    if errors:
        raise ValidationError(errors)
    return {
        "name": name,
        "email": email,
        "job_title": job_title,
        "division": division,
        "access_level": level,
    }


def get_user(conn: sqlite3.Connection, user_id: int):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User.from_row(row) if row else None


def get_user_by_matricula(conn: sqlite3.Connection, matricula: str):
    row = conn.execute(
        "SELECT * FROM users WHERE matricula = ? AND deleted_at IS NULL",
        ((matricula or "").strip().upper(),),
    ).fetchone()
    return User.from_row(row) if row else None


def _require_user(conn: sqlite3.Connection, user_id: int) -> User:
    user = get_user(conn, user_id)
    if user is None:
        raise UserNotFoundError(f"Usuário {user_id} não encontrado.")
    return user


def _next_matricula(conn: sqlite3.Connection, access_level: int) -> str:
    conn.execute(
        "UPDATE matricula_counters SET last_value = last_value + 1 WHERE access_level = ?",
        (access_level,),
    )
    sequence = conn.execute(
        "SELECT last_value FROM matricula_counters WHERE access_level = ?",
        (access_level,),
    ).fetchone()["last_value"]
    return f"{MATRICULA_PREFIXES[access_level]}{sequence:03d}"


def create_pending_user(
    conn: sqlite3.Connection,
    *,
    name,
    birth_date,
    cpf_encrypted,
    cpf_digest,
    rg_encrypted,
    email,
    job_title,
    division,
    password_hash,
    access_level,
) -> User:
    data = validate_profile(
        name=name, email=email, job_title=job_title, division=division,
        access_level=access_level,
    )
    if conn.execute("SELECT 1 FROM users WHERE email = ? COLLATE NOCASE", (data["email"],)).fetchone():
        raise ValidationError({"email": "Já existe um cadastro com este e-mail."})
    if conn.execute("SELECT 1 FROM users WHERE cpf_digest = ?", (cpf_digest,)).fetchone():
        raise ValidationError({"cpf": "Já existe um cadastro com este CPF."})
    if not password_hash:
        raise ValidationError({"password": "Não foi possível proteger a senha."})

    try:
        conn.execute("BEGIN IMMEDIATE")
        matricula = _next_matricula(conn, data["access_level"])
        now = now_iso()
        cursor = conn.execute(
            """
            INSERT INTO users (
                matricula, name, birth_date, cpf_encrypted, cpf_digest, rg_encrypted,
                email, job_title, division, password_hash, role, access_level,
                status, active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                matricula, data["name"], birth_date, cpf_encrypted, cpf_digest,
                rg_encrypted, data["email"], data["job_title"], data["division"],
                password_hash, ROLE_USER, data["access_level"], STATUS_PENDING, now, now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        if "email" in str(exc).lower():
            raise ValidationError({"email": "Já existe um cadastro com este e-mail."}) from exc
        if "cpf" in str(exc).lower():
            raise ValidationError({"cpf": "Já existe um cadastro com este CPF."}) from exc
        raise
    return _require_user(conn, cursor.lastrowid)


def create_provisioned_admin(
    conn: sqlite3.Connection, *, name, email, password_hash, access_level=3
) -> User:
    if not is_valid_level(access_level):
        raise ValidationError({"access_level": "Nível de acesso inválido."})
    clean_name = (name or "").strip()
    clean_email = (email or "").strip().lower()
    if not clean_name or not EMAIL_PATTERN.fullmatch(clean_email):
        raise ValidationError({"admin": "Nome e e-mail válidos são obrigatórios."})
    if not password_hash:
        raise ValidationError({"password": "A senha deve ser protegida antes de armazenar."})
    if conn.execute("SELECT 1 FROM users WHERE email = ? COLLATE NOCASE", (clean_email,)).fetchone():
        raise ValidationError({"email": "Já existe um usuário com este e-mail."})
    conn.execute("BEGIN IMMEDIATE")
    matricula = _next_matricula(conn, access_level)
    now = now_iso()
    cursor = conn.execute(
        """
        INSERT INTO users (
            matricula, name, email, job_title, division, password_hash, role,
            access_level, status, active, created_at, updated_at
        ) VALUES (?, ?, ?, 'Administrador', 'Administração', ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            matricula, clean_name, clean_email, password_hash, ROLE_ADMIN,
            access_level, STATUS_APPROVED, now, now,
        ),
    )
    conn.commit()
    return _require_user(conn, cursor.lastrowid)


def list_users(
    conn: sqlite3.Connection, *, status=None, level=None, query=None,
    order="name", direction="asc", limit=100, offset=0,
) -> list[User]:
    allowed_order = {
        "name": "name COLLATE NOCASE",
        "matricula": "matricula",
        "level": "access_level",
        "status": "status",
        "created": "created_at",
        "activity": "last_activity_at",
    }
    clauses = ["1 = 1"]
    params = []
    if status in (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_SUSPENDED, STATUS_INACTIVE):
        clauses.append("status = ?")
        params.append(status)
    if is_valid_level(level):
        clauses.append("access_level = ?")
        params.append(level)
    if query:
        clauses.append("(name LIKE ? OR matricula LIKE ? OR email LIKE ?)")
        needle = f"%{query.strip()}%"
        params.extend((needle, needle, needle))
    order_clause = allowed_order.get(order, allowed_order["name"])
    direction_clause = "DESC" if direction.lower() == "desc" else "ASC"
    rows = conn.execute(
        f"SELECT * FROM users WHERE {' AND '.join(clauses)} "
        f"ORDER BY {order_clause} {direction_clause} LIMIT ? OFFSET ?",
        (*params, max(1, min(int(limit), 200)), max(0, int(offset))),
    ).fetchall()
    return [User.from_row(row) for row in rows]


def list_pending_users(conn: sqlite3.Connection) -> list[User]:
    rows = conn.execute(
        "SELECT * FROM users WHERE status = ? AND deleted_at IS NULL ORDER BY created_at",
        (STATUS_PENDING,),
    ).fetchall()
    return [User.from_row(row) for row in rows]


def list_recent_users(conn: sqlite3.Connection, limit: int = 5) -> list[User]:
    return list_users(conn, order="created", direction="desc", limit=limit)


def count_users(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """
        SELECT COUNT(*) total,
            SUM(status = 'PENDING' AND deleted_at IS NULL) pending,
            SUM(status = 'APPROVED' AND deleted_at IS NULL) approved,
            SUM(status = 'REJECTED' AND deleted_at IS NULL) rejected,
            SUM(status = 'SUSPENDED' AND deleted_at IS NULL) suspended,
            SUM((status = 'INACTIVE' OR deleted_at IS NOT NULL) AND status != 'PENDING') inactive
        FROM users
        """
    ).fetchone()
    by_level = {
        item["access_level"]: item["count"]
        for item in conn.execute(
            "SELECT access_level, COUNT(*) count FROM users "
            "WHERE deleted_at IS NULL GROUP BY access_level"
        )
    }
    return {key: row[key] or 0 for key in row.keys()} | {"by_level": by_level}


def biometric_status(conn: sqlite3.Connection, user_id: int) -> str:
    count = conn.execute(
        "SELECT COUNT(*) FROM biometric_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    return "CADASTRADA" if count == 3 else ("PARCIAL" if count else "NÃO CADASTRADA")


def approve_user(conn: sqlite3.Connection, *, admin_id: int, user_id: int) -> User:
    user = _require_user(conn, user_id)
    if user.status != STATUS_PENDING:
        raise ValidationError({"status": "Somente cadastros pendentes podem ser aprovados."})
    if biometric_status(conn, user_id) != "CADASTRADA":
        raise ValidationError({"biometric": "O cadastro biométrico precisa das três etapas."})
    now = now_iso()
    conn.execute(
        "UPDATE users SET status = ?, active = 1, approved_by = ?, approved_at = ?, "
        "updated_at = ? WHERE id = ?",
        (STATUS_APPROVED, admin_id, now, now, user_id),
    )
    audit_service.record_admin_action(
        conn, admin_id=admin_id, target_user_id=user_id, action="ADMIN_APPROVE_USER",
        before={"status": user.status}, after={"status": STATUS_APPROVED},
    )
    conn.commit()
    return _require_user(conn, user_id)


def reject_user(
    conn: sqlite3.Connection, *, admin_id: int, user_id: int, reason: str
) -> User:
    user = _require_user(conn, user_id)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Informe a justificativa da rejeição."})
    if user.status != STATUS_PENDING:
        raise ValidationError({"status": "Somente cadastros pendentes podem ser rejeitados."})
    now = now_iso()
    conn.execute(
        "UPDATE users SET status = ?, active = 0, rejection_reason = ?, updated_at = ? WHERE id = ?",
        (STATUS_REJECTED, reason[:500], now, user_id),
    )
    audit_service.record_admin_action(
        conn, admin_id=admin_id, target_user_id=user_id, action="ADMIN_REJECT_USER",
        before={"status": user.status}, after={"status": STATUS_REJECTED}, reason=reason,
    )
    conn.commit()
    return _require_user(conn, user_id)


def update_user(
    conn: sqlite3.Connection, *, admin_id: int, user_id: int,
    name, email, birth_date, cpf_encrypted, cpf_digest, rg_encrypted,
    job_title, division, access_level,
) -> User:
    current = _require_user(conn, user_id)
    data = validate_profile(
        name=name, email=email, job_title=job_title, division=division,
        access_level=access_level,
    )
    if conn.execute(
        "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE AND id != ?",
        (data["email"], user_id),
    ).fetchone():
        raise ValidationError({"email": "Já existe um usuário com este e-mail."})
    if cpf_digest and conn.execute(
        "SELECT 1 FROM users WHERE cpf_digest = ? AND id != ?", (cpf_digest, user_id)
    ).fetchone():
        raise ValidationError({"cpf": "Já existe um cadastro com este CPF."})
    before = {
        "name": current.name, "email": current.email, "access_level": current.access_level,
        "status": current.status,
    }
    now = now_iso()
    conn.execute(
        """
        UPDATE users SET name = ?, email = ?, birth_date = ?, cpf_encrypted = COALESCE(?, cpf_encrypted),
            cpf_digest = COALESCE(?, cpf_digest), rg_encrypted = COALESCE(?, rg_encrypted),
            job_title = ?, division = ?, access_level = ?, updated_at = ? WHERE id = ?
        """,
        (
            data["name"], data["email"], birth_date, cpf_encrypted, cpf_digest, rg_encrypted,
            data["job_title"], data["division"], data["access_level"], now, user_id,
        ),
    )
    after = {
        "name": data["name"], "email": data["email"], "access_level": data["access_level"],
        "status": current.status,
    }
    action = "ADMIN_CHANGE_LEVEL" if before["access_level"] != after["access_level"] else "ADMIN_EDIT_USER"
    audit_service.record_admin_action(
        conn, admin_id=admin_id, target_user_id=user_id, action=action,
        before=before, after=after,
    )
    conn.commit()
    return _require_user(conn, user_id)


def set_user_status(
    conn: sqlite3.Connection, *, admin_id: int, user_id: int, status: str, reason: str = ""
) -> User:
    current = _require_user(conn, user_id)
    if status not in (STATUS_SUSPENDED, STATUS_INACTIVE, STATUS_APPROVED):
        raise ValidationError({"status": "Transição de status inválida."})
    if status == STATUS_SUSPENDED and not reason.strip():
        raise ValidationError({"reason": "Informe o motivo da suspensão."})
    if status == STATUS_APPROVED and biometric_status(conn, user_id) != "CADASTRADA":
        raise ValidationError({"biometric": "A reativação exige as três capturas biométricas."})
    if current.is_admin and current.status == STATUS_APPROVED and status != STATUS_APPROVED:
        admins = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = ? AND status = ? AND deleted_at IS NULL",
            (ROLE_ADMIN, STATUS_APPROVED),
        ).fetchone()[0]
        if admins <= 1:
            raise ValidationError({"status": "Não é possível remover o último administrador ativo."})
    now = now_iso()
    deleted_at = now if status == STATUS_INACTIVE else None
    conn.execute(
        "UPDATE users SET status = ?, active = ?, deleted_at = ?, rejection_reason = ?, updated_at = ? "
        "WHERE id = ?",
        (
            status, int(status == STATUS_APPROVED), deleted_at,
            reason.strip()[:500] or None, now, user_id,
        ),
    )
    audit_service.record_admin_action(
        conn, admin_id=admin_id, target_user_id=user_id,
        action={
            STATUS_SUSPENDED: "ADMIN_SUSPEND_USER",
            STATUS_INACTIVE: "ADMIN_DEACTIVATE_USER",
            STATUS_APPROVED: "ADMIN_REACTIVATE_USER",
        }[status],
        before={"status": current.status}, after={"status": status}, reason=reason,
    )
    conn.commit()
    return _require_user(conn, user_id)
