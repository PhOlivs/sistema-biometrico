"""Security and administrative audit event persistence."""

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_access(
    conn,
    *,
    event: str,
    result: str,
    user_id=None,
    matricula=None,
    resource_id=None,
    required_level=None,
    auth_type=None,
    details=None,
) -> None:
    conn.execute(
        """
        INSERT INTO access_logs (
            user_id, matricula, event, result, resource_id, required_level,
            auth_type, details, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, matricula, event, result, resource_id, required_level,
            auth_type, json.dumps(details, ensure_ascii=False) if details else None, _now(),
        ),
    )


def record_admin_action(
    conn,
    *,
    admin_id: int,
    target_user_id: int | None,
    action: str,
    before=None,
    after=None,
    reason: str | None = None,
    result: str = "SUCCESS",
) -> None:
    conn.execute(
        """
        INSERT INTO admin_actions (
            admin_id, target_user_id, action, before_data, after_data,
            reason, result, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            admin_id, target_user_id, action,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False) if after is not None else None,
            reason, result, _now(),
        ),
    )
    record_access(
        conn, event=action, result=result, user_id=admin_id,
        details={"target_user_id": target_user_id, "reason": reason} if reason else {
            "target_user_id": target_user_id
        },
    )


def list_access_logs(conn, *, event=None, result=None, matricula=None, user_query=None,
                     level=None, start=None, end=None, limit=100, offset=0):
    clauses = ["1 = 1"]
    params = []
    if event:
        clauses.append("l.event = ?")
        params.append(event)
    if result in ("SUCCESS", "DENIED", "FAILURE", "INFO"):
        clauses.append("l.result = ?")
        params.append(result)
    if matricula:
        clauses.append("l.matricula = ?")
        params.append(matricula.strip().upper())
    if user_query:
        clauses.append("(u.name LIKE ? OR l.matricula LIKE ?)")
        needle = f"%{user_query.strip()}%"
        params.extend((needle, needle))
    if level in (1, 2, 3):
        clauses.append("u.access_level = ?")
        params.append(level)
    if start:
        clauses.append("l.created_at >= ?")
        params.append(start)
    if end:
        clauses.append("l.created_at < ?")
        params.append(f"{end}T24" if len(end) == 10 else end)
    return conn.execute(
        f"""
        SELECT l.*, u.name AS user_name, u.access_level AS user_level,
               t.name AS resource_name
        FROM access_logs l
        LEFT JOIN users u ON u.id = l.user_id
        LEFT JOIN toxins t ON t.id = l.resource_id
        WHERE {' AND '.join(clauses)}
        ORDER BY l.created_at DESC LIMIT ? OFFSET ?
        """,
        (*params, max(1, min(int(limit), 200)), max(0, int(offset))),
    ).fetchall()


def access_summary(conn) -> dict:
    result_counts = {
        row["result"]: row["count"]
        for row in conn.execute("SELECT result, COUNT(*) count FROM access_logs GROUP BY result")
    }
    events = {
        row["event"]: row["count"]
        for row in conn.execute("SELECT event, COUNT(*) count FROM access_logs GROUP BY event")
    }
    recent = conn.execute(
        "SELECT event, result, created_at FROM access_logs ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    by_level = {
        row["user_level"]: row["count"]
        for row in conn.execute(
            "SELECT u.access_level user_level, COUNT(*) count FROM access_logs l "
            "JOIN users u ON u.id = l.user_id GROUP BY u.access_level"
        )
    }
    return {
        "results": result_counts,
        "events": events,
        "recent": recent,
        "by_level": by_level,
    }
