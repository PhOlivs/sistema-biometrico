"""
Regras de negócio relacionadas a usuários.

Fluxo:  rota Flask  ->  user_service  ->  database

Este serviço valida os dados e decide o que é permitido. Ele não conhece
HTML nem requisições HTTP, e não faz reconhecimento facial. Todas as
funções recebem a conexão SQLite como primeiro argumento, o que facilita
testá-las com um banco temporário.

Revogar o acesso de alguém = desativar o usuário (active = 0). O registro
não é apagado, para preservar o histórico que a auditoria vai precisar.
"""

import re
import sqlite3
from datetime import datetime

from models.access_level import is_valid_level
from models.user import ROLE_ADMIN, VALID_ROLES, User

MAX_NAME_LENGTH = 120
MAX_EMAIL_LENGTH = 254
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Usuário criado apenas para desenvolvimento, quando o banco está vazio.
DEFAULT_ADMIN = {
    "name": "Administrador do Sistema",
    "email": "admin@bioauth.local",
    "role": ROLE_ADMIN,
    "access_level": 3,
}


class ValidationError(Exception):
    """Dados inválidos. `errors` mapeia nome do campo -> mensagem amigável."""

    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__("; ".join(errors.values()))


class UserNotFoundError(Exception):
    """Nenhum usuário com o id informado."""


# ----------------------------------------------------------------------
# Validação
# ----------------------------------------------------------------------

def _parse_access_level(raw):
    """Converte o valor recebido em int, ou devolve None se não for número.

    Aceita int e texto de dígitos (vindo de formulário HTML). Não decide se
    o nível é válido: isso é papel de is_valid_level().
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and re.fullmatch(r"[0-9]+", raw.strip()):
        return int(raw.strip())
    return None


def _clean_user_data(name, email, role, access_level) -> dict:
    """Valida e normaliza os dados de um usuário.

    Retorna um dicionário limpo ou levanta ValidationError com TODOS os
    erros encontrados (não apenas o primeiro).
    """
    errors = {}

    name = (name or "").strip()
    email = (email or "").strip().lower()
    role = (role or "").strip()
    level = _parse_access_level(access_level)

    if not name:
        errors["name"] = "Informe o nome completo."
    elif len(name) > MAX_NAME_LENGTH:
        errors["name"] = f"O nome deve ter no máximo {MAX_NAME_LENGTH} caracteres."

    if not email:
        errors["email"] = "Informe o e-mail."
    elif len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
        errors["email"] = "Informe um e-mail válido."

    if role not in VALID_ROLES:
        errors["role"] = "Perfil inválido."

    if not is_valid_level(level):
        errors["access_level"] = "Nível de acesso inválido. Use 1, 2 ou 3."

    if errors:
        raise ValidationError(errors)

    return {"name": name, "email": email, "role": role, "access_level": level}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ----------------------------------------------------------------------
# Consultas
# ----------------------------------------------------------------------

def get_user(conn: sqlite3.Connection, user_id: int):
    """Retorna o User ou None se não existir."""
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User.from_row(row) if row else None


def _require_user(conn: sqlite3.Connection, user_id: int) -> User:
    user = get_user(conn, user_id)
    if user is None:
        raise UserNotFoundError(f"Usuário {user_id} não encontrado.")
    return user


def list_users(conn: sqlite3.Connection) -> list:
    """Todos os usuários, em ordem alfabética."""
    rows = conn.execute("SELECT * FROM users ORDER BY name COLLATE NOCASE").fetchall()
    return [User.from_row(row) for row in rows]


def list_recent_users(conn: sqlite3.Connection, limit: int = 5) -> list:
    """Os últimos usuários cadastrados (mais recentes primeiro)."""
    rows = conn.execute(
        "SELECT * FROM users ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [User.from_row(row) for row in rows]


def count_users(conn: sqlite3.Connection) -> dict:
    """Totais para o painel: total, ativos e inativos."""
    row = conn.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(active), 0) AS active FROM users"
    ).fetchone()
    return {
        "total": row["total"],
        "active": row["active"],
        "inactive": row["total"] - row["active"],
    }


def _email_taken(conn, email: str, exclude_id=None) -> bool:
    """True se outro usuário já usa este e-mail (sem diferenciar maiúsculas)."""
    query = "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE"
    params = [email]
    if exclude_id is not None:
        query += " AND id != ?"
        params.append(exclude_id)
    return conn.execute(query, params).fetchone() is not None


def _is_last_active_admin(conn, user: User) -> bool:
    """True se `user` é o único ADMIN ativo do sistema."""
    if not (user.is_admin and user.active):
        return False
    total = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = ? AND active = 1", (ROLE_ADMIN,)
    ).fetchone()[0]
    return total <= 1


# ----------------------------------------------------------------------
# Operações
# ----------------------------------------------------------------------

def create_user(conn, name, email, role, access_level) -> User:
    """Cadastra um usuário ativo. Levanta ValidationError se algo for inválido."""
    data = _clean_user_data(name, email, role, access_level)

    if _email_taken(conn, data["email"]):
        raise ValidationError({"email": "Já existe um usuário com este e-mail."})

    now = _now()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, role, access_level, active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?)",
            (data["name"], data["email"], data["role"], data["access_level"], now, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Corrida entre duas requisições com o mesmo e-mail: o UNIQUE do banco decide.
        conn.rollback()
        raise ValidationError({"email": "Já existe um usuário com este e-mail."})

    return _require_user(conn, cursor.lastrowid)


def update_user(conn, user_id, name, email, role, access_level) -> User:
    """Atualiza nome, e-mail, perfil e nível de um usuário existente."""
    current = _require_user(conn, user_id)
    data = _clean_user_data(name, email, role, access_level)

    if _email_taken(conn, data["email"], exclude_id=user_id):
        raise ValidationError({"email": "Já existe um usuário com este e-mail."})

    if data["role"] != ROLE_ADMIN and _is_last_active_admin(conn, current):
        raise ValidationError(
            {"role": "Não é possível remover o perfil do único administrador ativo."}
        )

    try:
        conn.execute(
            "UPDATE users SET name = ?, email = ?, role = ?, access_level = ?, updated_at = ? "
            "WHERE id = ?",
            (data["name"], data["email"], data["role"], data["access_level"], _now(), user_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValidationError({"email": "Já existe um usuário com este e-mail."})

    return _require_user(conn, user_id)


def _set_active(conn, user_id: int, active: bool) -> User:
    conn.execute(
        "UPDATE users SET active = ?, updated_at = ? WHERE id = ?",
        (1 if active else 0, _now(), user_id),
    )
    conn.commit()
    return _require_user(conn, user_id)


def activate_user(conn, user_id: int) -> User:
    """Reativa um usuário."""
    _require_user(conn, user_id)
    return _set_active(conn, user_id, True)


def deactivate_user(conn, user_id: int) -> User:
    """Desativa um usuário (revoga o acesso sem apagar o registro)."""
    user = _require_user(conn, user_id)
    if _is_last_active_admin(conn, user):
        raise ValidationError(
            {"active": "Não é possível desativar o único administrador ativo."}
        )
    return _set_active(conn, user_id, False)


def ensure_default_admin(conn):
    """Cria o administrador de desenvolvimento se o banco não tem usuários.

    Só age quando a tabela está vazia, para não recriar o administrador
    depois que alguém o renomear ou desativar de propósito.
    Retorna o User criado, ou None se nada foi feito.
    """
    if count_users(conn)["total"] > 0:
        return None
    return create_user(conn, **DEFAULT_ADMIN)
