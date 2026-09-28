"""
Persistência SQLite do BIOAUTH.

Este módulo cuida apenas do ARMAZENAMENTO: abrir/fechar conexões e criar
as tabelas. Regras de negócio (validar e-mail, impedir desativar o último
administrador, etc.) ficam em services/.

O banco fica em database/bioauth.db (caminho definido em config/config.py)
e não é versionado no Git.
"""

import os
import sqlite3

from flask import current_app, g

# As restrições CHECK são uma segunda linha de defesa: mesmo que uma
# validação do backend falhe, o SQLite recusa valores fora do permitido.
# Os valores abaixo precisam acompanhar models/user.py e models/access_level.py.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    email        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    role         TEXT    NOT NULL CHECK (role IN ('ADMIN', 'USER')),
    access_level INTEGER NOT NULL CHECK (access_level IN (1, 2, 3)),
    active       INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    """Abre uma conexão com o arquivo SQLite indicado.

    Recebe o caminho como parâmetro para que os testes possam usar um
    banco temporário sem tocar no banco real.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # permite acessar colunas por nome
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Cria as tabelas, caso ainda não existam (é seguro chamar sempre)."""
    conn.executescript(SCHEMA)
    conn.commit()


def get_db() -> sqlite3.Connection:
    """Conexão da requisição atual (aberta na primeira chamada)."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_error=None) -> None:
    """Fecha a conexão ao final da requisição."""
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app) -> None:
    """Registra o fechamento automático da conexão no Flask."""
    app.teardown_appcontext(close_db)
