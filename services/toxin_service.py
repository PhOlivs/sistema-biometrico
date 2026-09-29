"""Classification-aware access to fictional, non-operational records."""

from services import access_service, audit_service


def list_accessible(conn, user):
    rows = conn.execute(
        "SELECT * FROM toxins WHERE status = 'ATIVO' AND access_level <= ? ORDER BY access_level, name",
        (user.access_level,),
    ).fetchall()
    return rows


def get_toxin(conn, toxin_id: int):
    return conn.execute(
        "SELECT * FROM toxins WHERE id = ? AND status = 'ATIVO'", (toxin_id,)
    ).fetchone()


def request_access(conn, *, user, toxin_id: int):
    toxin = get_toxin(conn, toxin_id)
    if toxin is None:
        audit_service.record_access(
            conn, event="TOXIN_ACCESS", result="FAILURE", user_id=user.id,
            matricula=user.matricula, resource_id=None, auth_type="SESSION",
            details={"reason": "RESOURCE_NOT_FOUND"},
        )
        conn.commit()
        return None, False
    allowed = access_service.user_can_access(user, toxin["access_level"])
    audit_service.record_access(
        conn,
        event="TOXIN_ACCESS" if allowed else "SUPERIOR_LEVEL_ATTEMPT",
        result="SUCCESS" if allowed else "DENIED",
        user_id=user.id,
        matricula=user.matricula,
        resource_id=toxin["id"],
        required_level=toxin["access_level"],
        auth_type="SESSION",
    )
    conn.commit()
    return toxin, allowed
