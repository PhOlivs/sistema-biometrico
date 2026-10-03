"""Public registration, multi-factor sign-in and user-facing pages."""

from flask import (
    Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template,
    request, session, url_for,
)

from database.database import get_db
from models.user import STATUS_APPROVED, STATUS_PENDING
from services import audit_service, auth_service, biometric_service, user_service
from services.toxin_service import list_accessible, request_access
from routes.decorators import login_required

auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/")
def index():
    return render_template(
        "index.html",
        biometric_ready=biometric_service.is_available(current_app.config),
    )


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def register():
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        try:
            user = auth_service.register_user(get_db(), dict(request.form))
        except user_service.ValidationError as exc:
            return render_template("register.html", form=form, errors=exc.errors), 400
        session["registration_user_id"] = user.id
        return redirect(url_for("auth.registration_biometric"))
    return render_template("register.html", form=form, errors={})


@auth_bp.get("/cadastro/biometria")
def registration_biometric():
    user_id = session.get("registration_user_id")
    user = user_service.get_user(get_db(), user_id) if user_id else None
    if user is None or user.status != STATUS_PENDING:
        return redirect(url_for("auth.register"))
    return render_template(
        "biometric_capture.html", mode="enroll", user=user,
        biometric_ready=biometric_service.is_available(current_app.config),
    )


@auth_bp.post("/api/biometrics/enroll")
def enroll_biometric():
    user_id = session.get("registration_user_id")
    user = user_service.get_user(get_db(), user_id) if user_id else None
    if user is None or user.status != STATUS_PENDING:
        return jsonify(error="Etapa de cadastro inválida ou expirada."), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Envie um objeto JSON com as três capturas."), 400
    try:
        biometric_service.enroll_user(
            get_db(), user_id=user.id, frames=payload.get("images", {}),
            config=current_app.config,
        )
    except ValueError as exc:
        audit_service.record_access(
            get_db(), event="BIOMETRIC_ENROLLMENT", result="FAILURE",
            user_id=user.id, matricula=user.matricula, auth_type="FACE",
            details={"reason": str(exc)},
        )
        get_db().commit()
        return jsonify(error=str(exc)), 400
    except RuntimeError as exc:
        current_app.logger.error("Biometric enrollment unavailable: %s", exc)
        audit_service.record_access(
            get_db(), event="BIOMETRIC_ENROLLMENT", result="FAILURE",
            user_id=user.id, matricula=user.matricula, auth_type="FACE",
            details={"reason": "BIOMETRIC_ENGINE_UNAVAILABLE"},
        )
        get_db().commit()
        return jsonify(error=str(exc)), 503
    audit_service.record_access(
        get_db(), event="BIOMETRIC_ENROLLMENT", result="SUCCESS",
        user_id=user.id, matricula=user.matricula, auth_type="FACE",
    )
    get_db().commit()
    session.pop("registration_user_id", None)
    session["registration_result"] = {
        "name": user.name,
    }
    return jsonify(redirect=url_for("auth.registration_complete"))


@auth_bp.get("/cadastro/concluido")
def registration_complete():
    result = session.pop("registration_result", None)
    if not result:
        return redirect(url_for("auth.index"))
    return render_template("registration_complete.html", result=result)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user, error = auth_service.verify_password(
            get_db(), matricula=request.form.get("matricula", ""),
            password=request.form.get("password", ""),
        )
        if error:
            return render_template("login.html", error=error, matricula=request.form.get("matricula", "")), 401
        session.clear()
        session["pending_auth_user_id"] = user.id
        return redirect(url_for("auth.authentication"))
    return render_template("login.html", error=None, matricula="")


@auth_bp.get("/autenticacao")
def authentication():
    pending_id = session.get("pending_auth_user_id")
    user = user_service.get_user(get_db(), pending_id) if pending_id else None
    if user is None or user.status != STATUS_APPROVED:
        return redirect(url_for("auth.login"))
    profile_count = get_db().execute(
        "SELECT COUNT(*) FROM biometric_profiles WHERE user_id = ?", (user.id,)
    ).fetchone()[0]
    if profile_count != 3 and not user.is_admin:
        flash("Seu perfil biométrico não está completo. Procure a administração.", "error")
        session.pop("pending_auth_user_id", None)
        return redirect(url_for("auth.login"))
    mode = "setup" if profile_count != 3 and user.is_admin else "verify"
    challenge = biometric_service.create_liveness_challenge() if mode == "verify" else []
    if challenge:
        session["face_liveness_challenge"] = challenge
    return render_template(
        "biometric_capture.html", mode=mode, user=user, liveness_challenge=challenge,
        biometric_ready=biometric_service.is_available(current_app.config),
    )


@auth_bp.post("/api/auth/face")
def verify_login_face():
    pending_id = session.get("pending_auth_user_id")
    user = user_service.get_user(get_db(), pending_id) if pending_id else None
    if user is None or user.status != STATUS_APPROVED:
        return jsonify(error="A etapa de senha expirou. Entre novamente."), 401
    challenge = session.pop("face_liveness_challenge", None)
    next_challenge = biometric_service.create_liveness_challenge()
    session["face_liveness_challenge"] = next_challenge
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(
            error="Envie a captura facial e as imagens do desafio de presença.",
            challenge=next_challenge,
        ), 400
    try:
        recognized, scores = biometric_service.verify_user(
            get_db(), user_id=user.id, frame=payload.get("image", ""),
            liveness_frames=payload.get("liveness_images"),
            challenge=challenge,
            config=current_app.config,
        )
    except ValueError as exc:
        audit_service.record_access(
            get_db(), event="BIOMETRIC_AUTHENTICATION", result="FAILURE",
            user_id=user.id, matricula=user.matricula, auth_type="FACE",
            details={"reason": str(exc), "liveness_challenge": challenge},
        )
        get_db().commit()
        return jsonify(error=str(exc), challenge=next_challenge), 400
    except RuntimeError as exc:
        current_app.logger.error("Biometric verification unavailable: %s", exc)
        audit_service.record_access(
            get_db(), event="BIOMETRIC_AUTHENTICATION", result="FAILURE",
            user_id=user.id, matricula=user.matricula, auth_type="FACE",
            details={"reason": "BIOMETRIC_ENGINE_UNAVAILABLE"},
        )
        get_db().commit()
        return jsonify(
            error=str(exc), challenge=next_challenge,
        ), 503
    score_details = {
        key.lower(): round(value, 6)
        for key, value in scores.items()
    }
    audit_service.record_access(
        get_db(), event="BIOMETRIC_AUTHENTICATION",
        result="SUCCESS" if recognized else "FAILURE",
        user_id=user.id, matricula=user.matricula, auth_type="FACE",
        details={
            "liveness": "passed",
            "liveness_challenge": challenge,
            "face_scores": score_details,
        },
    )
    get_db().commit()
    if not recognized:
        return jsonify(
            error="A biometria não foi confirmada. Siga o novo desafio e tente novamente.",
            challenge=next_challenge,
        ), 401
    session.clear()
    session["user_id"] = user.id
    session.permanent = True
    auth_service.mark_login_complete(get_db(), user.id)
    destination = "admin.dashboard" if user.is_admin else "auth.dashboard"
    return jsonify(redirect=url_for(destination))


@auth_bp.post("/api/biometrics/admin-setup")
def setup_admin_biometric():
    pending_id = session.get("pending_auth_user_id")
    user = user_service.get_user(get_db(), pending_id) if pending_id else None
    if user is None or not user.is_admin or user.status != STATUS_APPROVED:
        return jsonify(error="Somente o primeiro administrador autenticado pode concluir este registro."), 403
    count = get_db().execute(
        "SELECT COUNT(*) FROM biometric_profiles WHERE user_id = ?", (user.id,)
    ).fetchone()[0]
    if count == 3:
        return jsonify(error="O perfil biométrico já está cadastrado."), 409
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Envie um objeto JSON com as três capturas."), 400
    try:
        biometric_service.enroll_user(
            get_db(), user_id=user.id, frames=payload.get("images", {}),
            config=current_app.config,
        )
    except ValueError as exc:
        audit_service.record_access(
            get_db(), event="BIOMETRIC_ENROLLMENT", result="FAILURE",
            user_id=user.id, matricula=user.matricula, auth_type="FACE",
            details={"reason": str(exc)},
        )
        get_db().commit()
        return jsonify(error=str(exc)), 400
    except RuntimeError as exc:
        current_app.logger.error("Admin biometric setup unavailable: %s", exc)
        audit_service.record_access(
            get_db(), event="BIOMETRIC_ENROLLMENT", result="FAILURE",
            user_id=user.id, matricula=user.matricula, auth_type="FACE",
            details={"reason": "BIOMETRIC_ENGINE_UNAVAILABLE"},
        )
        get_db().commit()
        return jsonify(error=str(exc)), 503
    audit_service.record_access(
        get_db(), event="BIOMETRIC_ENROLLMENT", result="SUCCESS",
        user_id=user.id, matricula=user.matricula, auth_type="FACE",
        details={"reason": "INITIAL_ADMIN_SETUP"},
    )
    get_db().commit()
    session.clear()
    session["user_id"] = user.id
    session.permanent = True
    auth_service.mark_login_complete(get_db(), user.id)
    return jsonify(redirect=url_for("admin.dashboard"))


@auth_bp.post("/logout")
@login_required
def logout():
    user = g.current_user
    audit_service.record_access(
        get_db(), event="LOGOUT", result="SUCCESS", user_id=user.id,
        matricula=user.matricula, auth_type="SESSION",
    )
    get_db().commit()
    session.clear()
    flash("Sessão encerrada.", "success")
    return redirect(url_for("auth.index"))


@auth_bp.get("/painel")
@login_required
def dashboard():
    if g.current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    return render_template("user/dashboard.html", user=g.current_user)


@auth_bp.get("/perfil")
@login_required
def profile():
    return render_template("user/profile.html", user=g.current_user)


@auth_bp.get("/toxinas")
@login_required
def toxins():
    return render_template(
        "user/toxins.html", user=g.current_user,
        toxins=list_accessible(get_db(), g.current_user),
    )


@auth_bp.get("/toxinas/<int:toxin_id>")
@login_required
def toxin_detail(toxin_id):
    toxin, allowed = request_access(get_db(), user=g.current_user, toxin_id=toxin_id)
    if toxin is None:
        abort(404)
    if not allowed:
        return render_template(
            "access_denied.html", user=g.current_user,
            required_level=toxin["access_level"],
        ), 403
    return render_template("user/toxin_detail.html", user=g.current_user, toxin=toxin)


@auth_bp.get("/api/toxins")
@login_required
def api_toxins():
    return jsonify([
        {
            "id": row["id"], "code": row["code"], "name": row["name"],
            "access_level": row["access_level"],
        }
        for row in list_accessible(get_db(), g.current_user)
    ])


@auth_bp.post("/api/access/<int:toxin_id>")
@login_required
def api_toxin_access(toxin_id):
    toxin, allowed = request_access(get_db(), user=g.current_user, toxin_id=toxin_id)
    if toxin is None:
        return jsonify(error="Registro não encontrado."), 404
    if not allowed:
        return jsonify(error="Autorização insuficiente.", required_level=toxin["access_level"]), 403
    return jsonify(
        id=toxin["id"], name=toxin["name"], description=toxin["description"],
        access_level=toxin["access_level"],
    )
