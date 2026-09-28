"""
Rotas do painel administrativo (/admin).

As rotas apenas recebem a requisição, chamam o user_service e escolhem
o template. Regras de negócio e SQL não ficam aqui.

ATENÇÃO: nesta fase o painel NÃO possui proteção de acesso. Qualquer
pessoa que alcance a aplicação consegue abrir /admin. Isso só é aceitável
em desenvolvimento local. O ponto único para a proteção futura é
require_admin(), executada antes de TODAS as rotas deste blueprint.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from database.database import get_db
from models.access_level import level_choices
from models.user import ROLE_LABELS, ROLE_USER
from services import user_service
from services.user_service import ValidationError

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

RECENT_USERS_ON_DASHBOARD = 5


@admin_bp.before_request
def require_admin():
    """Ponto único de proteção do painel administrativo.

    Hoje não verifica nada (painel aberto, apenas para desenvolvimento).
    Quando a autenticação administrativa existir, a verificação entra
    aqui, por exemplo: `abort(403)` se o usuário atual não for ADMIN.
    Retornar None significa "acesso liberado".
    """
    return None


def _form_context(form, errors, user=None):
    """Variáveis comuns do template do formulário de usuário."""
    return {
        "form": form,
        "errors": errors,
        "user": user,
        "roles": list(ROLE_LABELS.items()),
        "levels": level_choices(),
    }


def _read_form() -> dict:
    """Lê os campos do formulário como texto bruto (a validação é do serviço)."""
    return {
        "name": request.form.get("name", ""),
        "email": request.form.get("email", ""),
        "role": request.form.get("role", ""),
        "access_level": request.form.get("access_level", ""),
    }


def _get_user_or_404(user_id: int):
    user = user_service.get_user(get_db(), user_id)
    if user is None:
        abort(404)
    return user


# ----------------------------------------------------------------------
# Painel e listagem
# ----------------------------------------------------------------------

@admin_bp.route("")
def dashboard():
    conn = get_db()
    return render_template(
        "admin/dashboard.html",
        stats=user_service.count_users(conn),
        users=user_service.list_recent_users(conn, RECENT_USERS_ON_DASHBOARD),
    )


@admin_bp.route("/users")
def users():
    return render_template("admin/users.html", users=user_service.list_users(get_db()))


# ----------------------------------------------------------------------
# Cadastro e edição
# ----------------------------------------------------------------------

@admin_bp.route("/users/new", methods=["GET", "POST"])
def new_user():
    if request.method == "POST":
        form = _read_form()
        try:
            user = user_service.create_user(get_db(), **form)
        except ValidationError as exc:
            return render_template("admin/user_form.html", **_form_context(form, exc.errors)), 400
        flash(f"Usuário {user.name} cadastrado com sucesso.", "success")
        return redirect(url_for("admin.users"))

    form = {"name": "", "email": "", "role": ROLE_USER, "access_level": "1"}
    return render_template("admin/user_form.html", **_form_context(form, {}))


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
def edit_user(user_id):
    user = _get_user_or_404(user_id)

    if request.method == "POST":
        form = _read_form()
        try:
            updated = user_service.update_user(get_db(), user_id, **form)
        except ValidationError as exc:
            return render_template(
                "admin/user_form.html", **_form_context(form, exc.errors, user)
            ), 400
        flash(f"Usuário {updated.name} atualizado.", "success")
        return redirect(url_for("admin.users"))

    form = {
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "access_level": str(user.access_level),
    }
    return render_template("admin/user_form.html", **_form_context(form, {}, user))


# ----------------------------------------------------------------------
# Ativação e desativação
# ----------------------------------------------------------------------

@admin_bp.route("/users/<int:user_id>/deactivate", methods=["POST"])
def deactivate_user(user_id):
    _get_user_or_404(user_id)
    try:
        user = user_service.deactivate_user(get_db(), user_id)
        flash(f"Usuário {user.name} desativado.", "success")
    except ValidationError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/activate", methods=["POST"])
def activate_user(user_id):
    _get_user_or_404(user_id)
    user = user_service.activate_user(get_db(), user_id)
    flash(f"Usuário {user.name} reativado.", "success")
    return redirect(url_for("admin.users"))
