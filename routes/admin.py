"""Protected administrative dashboard, approvals, user management and audit."""

from flask import (
    Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template,
    request, send_file, url_for,
)
import base64
from io import BytesIO

from database.database import get_db
from models.user import STATUS_APPROVED
from services import audit_service, auth_service, organization_service, user_service

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
def require_admin():
    if g.current_user is None or g.current_user.status != STATUS_APPROVED:
        return redirect(url_for("auth.login"))
    if not g.current_user.is_admin:
        abort(403)
    return None


def _user_or_404(user_id):
    user = user_service.get_user(get_db(), user_id)
    if user is None:
        abort(404)
    return user


@admin_bp.get("/")
def dashboard():
    conn = get_db()
    return render_template(
        "admin/dashboard.html",
        stats=user_service.count_users(conn),
        audit=audit_service.access_summary(conn),
        users=user_service.list_recent_users(conn, 8),
        pending_count=user_service.count_users(conn)["pending"],
    )


@admin_bp.get("/solicitacoes")
def requests_list():
    conn = get_db()
    users = user_service.list_pending_users(conn)
    return render_template(
        "admin/requests.html",
        users=users,
        biometric_statuses={
            user.id: user_service.biometric_status(conn, user.id) for user in users
        },
    )


@admin_bp.get("/solicitacoes/<int:user_id>")
def request_detail(user_id):
    user = _user_or_404(user_id)
    return render_template(
        "admin/request_detail.html",
        user=user,
        biometric_status=user_service.biometric_status(get_db(), user.id),
        cpf_masked=_mask_cpf(auth_service.decrypt_sensitive(user.cpf_encrypted)),
        organization_options=organization_service.get_assignment_options(get_db()),
        form={},
        errors={},
    )


@admin_bp.get("/usuarios/<int:user_id>/foto")
def user_photo(user_id):
    user = _user_or_404(user_id)
    if not user.profile_photo_encrypted:
        abort(404)
    try:
        encoded = auth_service.decrypt_sensitive(
            bytes(user.profile_photo_encrypted).decode("ascii")
        )
        photo = base64.b64decode(encoded, validate=True)
    except (ValueError, UnicodeDecodeError):
        current_app.logger.error("Stored profile image for user %s is invalid.", user_id)
        abort(500)
    response = send_file(BytesIO(photo), mimetype="image/jpeg", max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@admin_bp.post("/solicitacoes/<int:user_id>/aprovar")
def approve(user_id):
    try:
        user = user_service.approve_user(
            get_db(), admin_id=g.current_user.id, user_id=user_id,
            access_level=None,
            position_code=request.form.get("position_code"),
            area_id=request.form.get("area_id"),
            team_id=request.form.get("team_id"),
            manager_user_id=request.form.get("manager_user_id"),
        )
    except user_service.ValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.request_detail", user_id=user_id))
    flash(
        f"Cadastro de {user.name} aprovado. Matrícula {user.matricula}; "
        "informe a matrícula ao usuário pelo canal institucional.",
        "success",
    )
    return redirect(url_for("admin.requests_list"))


@admin_bp.post("/solicitacoes/<int:user_id>/rejeitar")
def reject(user_id):
    try:
        user = user_service.reject_user(
            get_db(), admin_id=g.current_user.id, user_id=user_id,
            reason=request.form.get("reason", ""),
        )
    except user_service.ValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.request_detail", user_id=user_id))
    flash(f"Cadastro de {user.name} rejeitado.", "success")
    return redirect(url_for("admin.requests_list"))


@admin_bp.get("/usuarios")
def users():
    status = request.args.get("status") or None
    level = request.args.get("level", type=int)
    page = max(1, request.args.get("page", 1, type=int))
    rows = user_service.list_users(
        get_db(), status=status, level=level, query=request.args.get("q"),
        order=request.args.get("order", "name"),
        direction=request.args.get("direction", "asc"),
        limit=51, offset=(page - 1) * 50,
    )
    view = request.args.get("view", "table")
    return render_template(
        "admin/users.html",
        users=rows[:50],
        has_more=len(rows) > 50,
        page=page,
        filters=request.args,
        view=view,
        organization_chart=(
            organization_service.get_org_chart(get_db()) if view == "chart" else None
        ),
    )


@admin_bp.get("/usuarios/<int:user_id>")
def user_detail(user_id):
    user = _user_or_404(user_id)
    return render_template(
        "admin/user_detail.html",
        user=user,
        biometric_status=user_service.biometric_status(get_db(), user.id),
        cpf_masked=_mask_cpf(auth_service.decrypt_sensitive(user.cpf_encrypted)),
        rg_masked=_mask_rg(auth_service.decrypt_sensitive(user.rg_encrypted)),
    )


@admin_bp.route("/usuarios/<int:user_id>/editar", methods=["GET", "POST"])
def edit_user(user_id):
    user = _user_or_404(user_id)
    form = dict(request.form) if request.method == "POST" else {
        "name": user.name, "email": user.email, "birth_date": user.birth_date or "",
        "job_title": user.job_title, "division": user.division,
        "access_level": str(user.access_level) if user.access_level is not None else "",
        "cpf": "", "rg": "",
        "position_code": user.position_code or "",
        "area_id": str(user.area_id) if user.area_id else "",
        "team_id": str(user.team_id) if user.team_id else "",
        "manager_user_id": str(user.manager_user_id) if user.manager_user_id else "",
    }
    errors = {}
    if request.method == "POST":
        try:
            cpf = auth_service.normalize_cpf(form.get("cpf", "")) if form.get("cpf", "").strip() else None
            birth_date = form.get("birth_date", "").strip() or None
            if birth_date:
                birth_date = auth_service.validate_birth_date(birth_date)
            updated = user_service.update_user(
                get_db(), admin_id=g.current_user.id, user_id=user_id,
                name=form.get("name"), email=form.get("email"), birth_date=birth_date,
                cpf_encrypted=auth_service.encrypt_sensitive(cpf),
                cpf_digest=auth_service.cpf_digest(cpf) if cpf else None,
                rg_encrypted=auth_service.encrypt_sensitive(form.get("rg", "").strip() or None),
                job_title=form.get("job_title"), division=form.get("division"),
                access_level=form.get("access_level") or user.access_level,
                org_assignment={
                    "position_code": form.get("position_code"),
                    "area_id": form.get("area_id"),
                    "team_id": form.get("team_id"),
                    "manager_user_id": form.get("manager_user_id"),
                },
            )
        except user_service.ValidationError as exc:
            errors.update(exc.errors)
        except ValueError as exc:
            errors["cpf"] = str(exc)
        if not errors:
            flash(f"Perfil de {updated.name} atualizado.", "success")
            return redirect(url_for("admin.user_detail", user_id=user_id))
        return render_template(
            "admin/user_form.html", user=user, form=form, errors=errors,
            organization_options=organization_service.get_assignment_options(
                get_db(), exclude_user_id=user_id
            ),
        ), 400
    return render_template(
        "admin/user_form.html", user=user, form=form, errors=errors,
        organization_options=organization_service.get_assignment_options(
            get_db(), exclude_user_id=user_id
        ),
    )


@admin_bp.post("/usuarios/<int:user_id>/suspender")
def suspend_user(user_id):
    try:
        user = user_service.set_user_status(
            get_db(), admin_id=g.current_user.id, user_id=user_id,
            status="SUSPENDED", reason=request.form.get("reason", ""),
        )
    except user_service.ValidationError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Acesso de {user.name} suspenso.", "success")
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.post("/usuarios/<int:user_id>/reativar")
def reactivate_user(user_id):
    try:
        user = user_service.set_user_status(
            get_db(), admin_id=g.current_user.id, user_id=user_id,
            status=STATUS_APPROVED,
        )
    except user_service.ValidationError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Acesso de {user.name} reativado.", "success")
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.post("/usuarios/<int:user_id>/desativar")
def deactivate_user(user_id):
    try:
        user = user_service.set_user_status(
            get_db(), admin_id=g.current_user.id, user_id=user_id,
            status="INACTIVE", reason=request.form.get("reason", ""),
        )
    except user_service.ValidationError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Perfil de {user.name} desativado; o histórico foi preservado.", "success")
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.get("/acessos")
def access_logs():
    page = max(1, request.args.get("page", 1, type=int))
    filters = {
        "event": request.args.get("event") or None,
        "result": request.args.get("result") or None,
        "matricula": request.args.get("matricula") or None,
        "user_query": request.args.get("user") or None,
        "level": request.args.get("level", type=int),
        "start": request.args.get("start") or None,
        "end": request.args.get("end") or None,
    }
    rows = audit_service.list_access_logs(
        get_db(), **filters, limit=51, offset=(page - 1) * 50
    )
    return render_template(
        "admin/access_logs.html",
        logs=rows[:50],
        has_more=len(rows) > 50,
        page=page,
        filters=request.args,
    )


@admin_bp.get("/api/resumo")
def api_summary():
    conn = get_db()
    return jsonify(users=user_service.count_users(conn), access=audit_service.access_summary(conn))


@admin_bp.get("/api/acessos")
def api_access_logs():
    return jsonify([
        dict(row) for row in audit_service.list_access_logs(
            get_db(),
            event=request.args.get("event") or None,
            result=request.args.get("result") or None,
            matricula=request.args.get("matricula") or None,
            user_query=request.args.get("user") or None,
            level=request.args.get("level", type=int),
            start=request.args.get("start") or None,
            end=request.args.get("end") or None,
            limit=request.args.get("limit", default=100, type=int),
            offset=request.args.get("offset", default=0, type=int),
        )
    ])


def _mask_cpf(value):
    if not value:
        return "Não informado"
    digits = "".join(char for char in value if char.isdigit())
    return f"***.***.***-{digits[-2:]}" if len(digits) == 11 else "•••"


def _mask_rg(value):
    if not value:
        return "Não informado"
    return f"••••{value[-2:]}" if len(value) > 2 else "•••"
