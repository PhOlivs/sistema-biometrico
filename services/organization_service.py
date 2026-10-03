"""Organization assignments, reporting validation and chart construction."""

from models.user import STATUS_APPROVED, User


class OrganizationError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__("; ".join(errors.values()))


def get_assignment_options(conn, *, exclude_user_id: int | None = None) -> dict:
    positions = conn.execute(
        "SELECT code, name, access_level, scope FROM organization_positions "
        "WHERE active = 1 ORDER BY sort_order, name"
    ).fetchall()
    parent_codes = {
        row["subordinate_code"]: []
        for row in conn.execute(
            "SELECT subordinate.code AS subordinate_code, supervisor.code AS supervisor_code "
            "FROM organization_position_reports r "
            "JOIN organization_positions subordinate ON subordinate.id = r.subordinate_position_id "
            "JOIN organization_positions supervisor ON supervisor.id = r.supervisor_position_id"
        )
    }
    for row in conn.execute(
        "SELECT subordinate.code AS subordinate_code, supervisor.code AS supervisor_code "
        "FROM organization_position_reports r "
        "JOIN organization_positions subordinate ON subordinate.id = r.subordinate_position_id "
        "JOIN organization_positions supervisor ON supervisor.id = r.supervisor_position_id"
    ):
        parent_codes[row["subordinate_code"]].append(row["supervisor_code"])
    positions = [
        dict(row) | {"supervisor_codes": parent_codes.get(row["code"], [])}
        for row in positions
    ]
    position_groups = [
        {
            "label": f"NÍVEL {level}",
            "positions": [
                position for position in positions
                if position["access_level"] == level
                and position["scope"] != "GLOBAL"
                and position["code"] != "MANAGER"
            ],
        }
        for level in (1, 2, 3)
    ]
    position_groups.append({
        "label": "GESTÃO",
        "positions": [
            position for position in positions
            if position["scope"] == "GLOBAL" or position["code"] == "MANAGER"
        ],
    })
    areas = conn.execute(
        "SELECT id, code, name FROM organization_areas WHERE active = 1 ORDER BY name"
    ).fetchall()
    teams = conn.execute(
        "SELECT id, area_id, code, name FROM organization_teams "
        "WHERE active = 1 ORDER BY name"
    ).fetchall()
    params = [STATUS_APPROVED]
    exclusion = ""
    if exclude_user_id is not None:
        exclusion = "AND u.id != ?"
        params.append(exclude_user_id)
    supervisors = conn.execute(
        """
        SELECT u.id, u.name, u.matricula, u.area_id, u.team_id, p.code AS position_code,
               p.name AS position_name, p.scope AS position_scope, a.name AS area_name
        FROM users u
        JOIN organization_positions p ON p.id = u.position_id
        LEFT JOIN organization_areas a ON a.id = u.area_id
        WHERE u.status = ? AND u.deleted_at IS NULL AND u.access_level_assigned = 1
          AND p.active = 1
        """ + exclusion + " ORDER BY p.sort_order, u.name COLLATE NOCASE",
        params,
    ).fetchall()
    return {
        "positions": positions,
        "position_groups": position_groups,
        "areas": areas,
        "teams": teams,
        "supervisors": supervisors,
    }


def validate_assignment(
    conn,
    *,
    position_code,
    area_id,
    team_id,
    manager_user_id,
    access_level=None,
    target_user_id: int | None = None,
) -> dict:
    errors = {}
    position_code = (position_code or "").strip()
    position = conn.execute(
        "SELECT id, code, name, access_level, scope FROM organization_positions "
        "WHERE code = ? AND active = 1",
        (position_code,),
    ).fetchone()
    if not position:
        raise OrganizationError({"position_code": "Selecione um cargo hierárquico válido."})

    if access_level not in (None, ""):
        try:
            requested_level = int(access_level)
        except (TypeError, ValueError):
            requested_level = None
    else:
        requested_level = position["access_level"]
    if requested_level != position["access_level"]:
        errors["access_level"] = (
            f"O cargo {position['name']} deve possuir nível {position['access_level']}."
        )

    try:
        clean_area_id = int(area_id)
    except (TypeError, ValueError):
        clean_area_id = None
    try:
        clean_team_id = int(team_id)
    except (TypeError, ValueError):
        clean_team_id = None
    area = conn.execute(
        "SELECT id, name FROM organization_areas WHERE id = ? AND active = 1",
        (clean_area_id,),
    ).fetchone() if clean_area_id else None
    team = conn.execute(
        "SELECT id, name, area_id FROM organization_teams WHERE id = ? AND active = 1",
        (clean_team_id,),
    ).fetchone() if clean_team_id else None
    if not area:
        errors["area_id"] = "Selecione uma área válida."
    if not team:
        errors["team_id"] = "Selecione uma equipe válida."
    elif area and team["area_id"] != area["id"]:
        errors["team_id"] = "A equipe selecionada não pertence à área informada."

    parent_codes = [
        row["code"]
        for row in conn.execute(
            """
            SELECT supervisor.code
            FROM organization_position_reports r
            JOIN organization_positions supervisor ON supervisor.id = r.supervisor_position_id
            WHERE r.subordinate_position_id = ?
            """,
            (position["id"],),
        )
    ]
    supervisor = None
    if parent_codes:
        try:
            clean_manager_id = int(manager_user_id)
        except (TypeError, ValueError):
            clean_manager_id = None
        supervisor = conn.execute(
            """
            SELECT u.id, u.area_id, u.team_id, u.manager_user_id, p.code AS position_code,
                   p.scope AS position_scope
            FROM users u
            JOIN organization_positions p ON p.id = u.position_id
            WHERE u.id = ? AND u.status = 'APPROVED' AND u.deleted_at IS NULL
              AND u.access_level_assigned = 1
            """,
            (clean_manager_id,),
        ).fetchone() if clean_manager_id else None
        if not supervisor:
            errors["manager_user_id"] = "Selecione um superior hierárquico aprovado."
        elif supervisor["position_code"] not in parent_codes:
            errors["manager_user_id"] = "O cargo selecionado não pode receber este subordinado."
        elif (
            position["scope"] == "AREA"
            and supervisor["position_scope"] == "AREA"
            and area
            and supervisor["area_id"] != area["id"]
        ):
            errors["manager_user_id"] = "O superior deve pertencer à mesma área."
        elif (
            position["scope"] == "AREA"
            and supervisor["position_scope"] == "AREA"
            and team
            and supervisor["team_id"] != team["id"]
        ):
            errors["manager_user_id"] = "O superior deve pertencer à mesma equipe."
        elif target_user_id is not None and supervisor["id"] == target_user_id:
            errors["manager_user_id"] = "Uma pessoa não pode ser seu próprio superior."
    else:
        if manager_user_id not in (None, ""):
            errors["manager_user_id"] = "Este cargo não pode possuir um superior hierárquico."

    if not errors and target_user_id is not None and supervisor:
        current_id = supervisor["id"]
        visited = set()
        while current_id is not None:
            if current_id == target_user_id:
                errors["manager_user_id"] = "A relação criaria um ciclo hierárquico."
                break
            if current_id in visited:
                errors["manager_user_id"] = "A hierarquia existente contém um ciclo."
                break
            visited.add(current_id)
            row = conn.execute(
                "SELECT manager_user_id FROM users WHERE id = ?", (current_id,)
            ).fetchone()
            current_id = row["manager_user_id"] if row else None

    if errors:
        raise OrganizationError(errors)
    return {
        "position_id": position["id"],
        "position_code": position["code"],
        "position_name": position["name"],
        "position_scope": position["scope"],
        "area_id": area["id"],
        "area_name": area["name"],
        "team_id": team["id"],
        "team_name": team["name"],
        "manager_user_id": supervisor["id"] if supervisor else None,
        "access_level": position["access_level"],
    }


def validate_direct_reports(
    conn, *, user_id: int, new_position_id: int, new_position_scope: str,
    new_area_id: int, new_team_id: int,
) -> None:
    report = conn.execute(
        """
        SELECT u.id, u.area_id, u.team_id, subordinate.code AS position_code
        FROM users u
        JOIN organization_positions subordinate ON subordinate.id = u.position_id
        WHERE u.manager_user_id = ? AND u.deleted_at IS NULL
        """,
        (user_id,),
    ).fetchall()
    if not report:
        return
    allowed_codes = {
        row["code"]
        for row in conn.execute(
            """
            SELECT subordinate.code
            FROM organization_position_reports r
            JOIN organization_positions subordinate ON subordinate.id = r.subordinate_position_id
            WHERE r.supervisor_position_id = ?
            """,
            (new_position_id,),
        )
    }
    invalid_positions = [row["position_code"] for row in report if row["position_code"] not in allowed_codes]
    if invalid_positions:
        raise OrganizationError({
            "position_code": "O novo cargo não pode receber os subordinados atuais."
        })
    if new_position_scope == "AREA" and any(
        row["area_id"] != new_area_id for row in report
    ):
        raise OrganizationError({
            "area_id": "A mudança de área deixaria subordinados em outra área."
        })
    if new_position_scope == "AREA" and any(
        row["team_id"] != new_team_id for row in report
    ):
        raise OrganizationError({
            "team_id": "A mudança de equipe deixaria subordinados em outra equipe."
        })


def _joined_users(conn, *, with_position_only: bool):
    condition = "AND u.position_id IS NOT NULL" if with_position_only else ""
    return conn.execute(
        """
        SELECT u.*, p.code AS position_code, p.name AS position_name,
               p.sort_order AS position_sort_order, a.name AS area_name,
               t.name AS team_name, m.name AS manager_name
        FROM users u
        LEFT JOIN organization_positions p ON p.id = u.position_id
        LEFT JOIN organization_areas a ON a.id = u.area_id
        LEFT JOIN organization_teams t ON t.id = u.team_id
        LEFT JOIN users m ON m.id = u.manager_user_id
        WHERE u.deleted_at IS NULL
        """ + condition + " ORDER BY p.sort_order, u.name COLLATE NOCASE"
    ).fetchall()


def get_org_chart(conn) -> dict:
    rows = _joined_users(conn, with_position_only=True)
    by_id = {row["id"]: row for row in rows}
    children: dict[int, list] = {user_id: [] for user_id in by_id}
    roots = []
    for row in rows:
        manager_id = row["manager_user_id"]
        if manager_id in by_id and manager_id != row["id"]:
            children[manager_id].append(row)
        else:
            roots.append(row)

    visited = set()

    def build(row, ancestors=frozenset()):
        user = User.from_row(row)
        node = {"user": user, "children": []}
        visited.add(user.id)
        next_ancestors = ancestors | {user.id}
        for child in children[user.id]:
            if child["id"] not in next_ancestors and child["id"] not in visited:
                node["children"].append(build(child, next_ancestors))
        return node

    tree = [build(row) for row in roots]
    for row in rows:
        if row["id"] not in visited:
            tree.append(build(row))

    unassigned_rows = _joined_users(conn, with_position_only=False)
    unassigned = [
        User.from_row(row) for row in unassigned_rows if row["position_id"] is None
    ]
    return {"roots": tree, "unassigned": unassigned}
