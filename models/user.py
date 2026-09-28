"""
Modelo de usuário do BIOAUTH.

Um User representa uma IDENTIDADE CADASTRADA no sistema, não uma face.
Dados biométricos (embeddings) serão associados a ele em uma fase futura,
sem alterar esta classe.

Duas informações diferentes, que não devem ser confundidas:

    role          -> o que a pessoa pode fazer no sistema (ADMIN ou USER)
    access_level  -> quais recursos do cofre ela pode acessar (1, 2 ou 3)

Um administrador NÃO é "nível 4": ele tem role = ADMIN e um access_level
válido como qualquer outra pessoa.
"""

from dataclasses import dataclass

from models.access_level import level_label

ROLE_USER = "USER"
ROLE_ADMIN = "ADMIN"

ROLE_LABELS = {
    ROLE_USER: "Usuário",
    ROLE_ADMIN: "Administrador",
}

VALID_ROLES = tuple(ROLE_LABELS)


@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str
    role: str
    access_level: int
    active: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row) -> "User":
        """Cria um User a partir de uma linha do SQLite (sqlite3.Row)."""
        return cls(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            role=row["role"],
            access_level=row["access_level"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def role_label(self) -> str:
        return ROLE_LABELS[self.role]

    @property
    def access_level_label(self) -> str:
        return level_label(self.access_level)
