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
    access_level: int | None
    access_level_assigned: bool
    profile_photo_encrypted: bytes | None
    biometric_photo_consent_at: str | None
    status: str
    created_at: str
    updated_at: str
    last_activity_at: str | None = None
    cpf_encrypted: str | None = None
    rg_encrypted: str | None = None
    rejection_reason: str | None = None
    position_id: int | None = None
    position_code: str | None = None
    position_name: str | None = None
    area_id: int | None = None
    area_name: str | None = None
    team_id: int | None = None
    team_name: str | None = None
    manager_user_id: int | None = None
    manager_name: str | None = None

    @classmethod
    def from_row(cls, row) -> "User":
        columns = set(row.keys())
        return cls(
            id=row["id"],
            matricula=row["matricula"],
            name=row["name"],
            birth_date=row["birth_date"],
            email=row["email"],
            job_title=row["job_title"],
            division=row["division"],
            role=row["role"],
            access_level=row["access_level"] if bool(row["access_level_assigned"]) else None,
            access_level_assigned=bool(row["access_level_assigned"]),
            profile_photo_encrypted=row["profile_photo_encrypted"],
            biometric_photo_consent_at=row["biometric_photo_consent_at"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_activity_at=row["last_activity_at"],
            cpf_encrypted=row["cpf_encrypted"],
            rg_encrypted=row["rg_encrypted"],
            rejection_reason=row["rejection_reason"],
            position_id=row["position_id"],
            position_code=row["position_code"] if "position_code" in columns else None,
            position_name=row["position_name"] if "position_name" in columns else None,
            area_id=row["area_id"],
            area_name=row["area_name"] if "area_name" in columns else None,
            team_id=row["team_id"],
            team_name=row["team_name"] if "team_name" in columns else None,
            manager_user_id=row["manager_user_id"],
            manager_name=row["manager_name"] if "manager_name" in columns else None,
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
        return level_label(self.access_level) if self.access_level_assigned else "A definir"
