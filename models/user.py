"""User identity and lifecycle states."""

from dataclasses import dataclass

from models.access_level import level_label

ROLE_USER = "USER"
ROLE_ADMIN = "ADMIN"
ROLE_LABELS = {ROLE_USER: "Usuário", ROLE_ADMIN: "Administrador"}
VALID_ROLES = tuple(ROLE_LABELS)

STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_SUSPENDED = "SUSPENDED"
STATUS_INACTIVE = "INACTIVE"
VALID_STATUSES = (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_SUSPENDED,
    STATUS_INACTIVE,
)
STATUS_LABELS = {
    STATUS_PENDING: "Pendente",
    STATUS_APPROVED: "Aprovado",
    STATUS_REJECTED: "Rejeitado",
    STATUS_SUSPENDED: "Suspenso",
    STATUS_INACTIVE: "Inativo",
}


@dataclass(frozen=True)
class User:
    id: int
    matricula: str | None
    name: str
    birth_date: str | None
    email: str
    job_title: str
    division: str
    role: str
    access_level: int
    status: str
    created_at: str
    updated_at: str
    last_activity_at: str | None = None
    cpf_encrypted: str | None = None
    rg_encrypted: str | None = None
    rejection_reason: str | None = None

    @classmethod
    def from_row(cls, row) -> "User":
        return cls(
            id=row["id"],
            matricula=row["matricula"],
            name=row["name"],
            birth_date=row["birth_date"],
            email=row["email"],
            job_title=row["job_title"],
            division=row["division"],
            role=row["role"],
            access_level=row["access_level"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_activity_at=row["last_activity_at"],
            cpf_encrypted=row["cpf_encrypted"],
            rg_encrypted=row["rg_encrypted"],
            rejection_reason=row["rejection_reason"],
        )

    @property
    def active(self) -> bool:
        return self.status in (STATUS_PENDING, STATUS_APPROVED)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def role_label(self) -> str:
        return ROLE_LABELS[self.role]

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def access_level_label(self) -> str:
        return level_label(self.access_level)
