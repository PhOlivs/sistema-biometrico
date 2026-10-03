"""BIOAUTH Flask application factory and security middleware."""

import secrets

import click
from flask import Flask, abort, current_app, g, jsonify, render_template, request, session

from config.config import Config
from database import database
from models.user import STATUS_APPROVED
from routes.admin import admin_bp
from routes.auth import auth_bp
from services import audit_service, user_service
from werkzeug.security import generate_password_hash


def create_app(test_config: dict | None = None) -> Flask:
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)
    if test_config:
        flask_app.config.update(test_config)
    if not flask_app.config["DEBUG"] and (
        flask_app.config["SECRET_KEY"] == "desenvolvimento-local-nao-utilizar-em-producao"
        or not flask_app.config.get("DATA_ENCRYPTION_KEY")
    ):
        raise RuntimeError("Configure EGIDE_SECRET_KEY e EGIDE_DATA_ENCRYPTION_KEY fora do modo de desenvolvimento.")
    flask_app.config.setdefault("MAX_CONTENT_LENGTH", 18 * 1024 * 1024)
    flask_app.config["SESSION_COOKIE_HTTPONLY"] = True
    flask_app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    flask_app.config["SESSION_COOKIE_SECURE"] = not flask_app.config["DEBUG"]

    @flask_app.before_request
    def protect_requests():
        user_id = session.get("user_id")
        g.current_user = user_service.get_user(database.get_db(), user_id) if user_id else None
        if g.current_user and g.current_user.status != STATUS_APPROVED:
            session.pop("user_id", None)
            g.current_user = None
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = session.get("_csrf_token")
            submitted = request.headers.get("X-CSRFToken")
            if submitted is None:
                submitted = request.form.get("csrf_token")
            if not expected or not submitted or not secrets.compare_digest(expected, submitted):
                abort(400, description="Token de segurança inválido ou expirado. Atualize a página.")

    @flask_app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(self), microphone=(), geolocation=()"
        )
        return response

    @flask_app.context_processor
    def inject_template_globals():
        def csrf_token():
            if "_csrf_token" not in session:
                session["_csrf_token"] = secrets.token_urlsafe(32)
            return session["_csrf_token"]

        return {
            "system_name": flask_app.config["SYSTEM_NAME"],
            "system_subtitle": flask_app.config["SYSTEM_SUBTITLE"],
            "current_user": g.get("current_user"),
            "csrf_token": csrf_token,
        }

    @flask_app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @flask_app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @flask_app.errorhandler(413)
    def request_too_large(_error):
        message = "O envio ultrapassa o limite permitido."
        if request.is_json:
            return jsonify(error=message), 413
        return render_template("errors/413.html"), 413

    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(admin_bp)
    database.init_app(flask_app)
    with flask_app.app_context():
        database.init_db(database.get_db())

    @flask_app.cli.command("provision-admin")
    @click.option("--name", prompt="Nome completo")
    @click.option("--email", prompt="E-mail institucional (@egíde.com.br)")
    def provision_admin(name, email):
        """Create the first administrator from a local management terminal."""
        conn = database.get_db()
        existing = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'ADMIN' AND status = 'APPROVED' "
            "AND deleted_at IS NULL"
        ).fetchone()[0]
        if existing:
            raise click.ClickException("Já existe um administrador aprovado; provisionamento inicial recusado.")
        password = click.prompt("Senha (mínimo de 12 caracteres)", hide_input=True, confirmation_prompt=True)
        if len(password) < 12:
            raise click.ClickException("A senha deve ter pelo menos 12 caracteres.")
        try:
            user = user_service.create_provisioned_admin(
                conn, name=name, email=email,
                password_hash=generate_password_hash(password, method="scrypt"),
            )
        except user_service.ValidationError as exc:
            raise click.ClickException(str(exc)) from exc
        audit_service.record_admin_action(
            conn, admin_id=user.id, target_user_id=user.id,
            action="ADMIN_PROVISIONED",
            after={"role": user.role, "access_level": user.access_level},
        )
        conn.commit()
        click.echo(
            f"Administrador criado ({user.matricula}). Conclua o registro facial no primeiro login."
        )

    return flask_app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=app.config["DEBUG"], host="127.0.0.1", port=5000)
