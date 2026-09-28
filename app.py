"""
BIOAUTH - Sistema de Identificação e Autenticação Biométrica
--------------------------------------------------------------
Protótipo acadêmico desenvolvido para a disciplina de
Processamento de Imagem e Visão Computacional (PIVC).

Este arquivo é responsável apenas por:
  - criar e configurar a aplicação Flask (create_app);
  - preparar o banco de dados;
  - registrar as rotas.

A lógica de negócio fica em services/, models/ e biometric/.
As rotas administrativas ficam em routes/admin.py.

FASE ATUAL: Fase 4 - Usuários, administração e níveis de acesso.
Reconhecimento facial ainda NÃO está implementado.
"""

from flask import Flask, current_app, render_template

from config.config import Config
from database import database
from routes.admin import admin_bp
from services import user_service


def inject_branding():
    """Disponibiliza o nome do sistema em todos os templates."""
    return {
        "system_name": current_app.config["SYSTEM_NAME"],
        "system_subtitle": current_app.config["SYSTEM_SUBTITLE"],
    }


def index():
    """Página inicial do BIOAUTH."""
    return render_template("index.html")


def authentication():
    """Tela de autenticação (webcam ativa; reconhecimento ainda não implementado)."""
    return render_template("authentication.html")


def create_app(test_config: dict | None = None) -> Flask:
    """Fábrica da aplicação Flask.

    `test_config` permite que os testes sobrescrevam configurações
    (por exemplo, apontar DATABASE_PATH para um banco temporário).
    Nada é criado ao apenas importar este módulo.
    """
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)
    if test_config:
        flask_app.config.update(test_config)

    flask_app.context_processor(inject_branding)

    # Rotas públicas (os nomes de endpoint são usados por url_for nos templates)
    flask_app.add_url_rule("/", endpoint="index", view_func=index)
    flask_app.add_url_rule("/autenticacao", endpoint="authentication", view_func=authentication)
    flask_app.register_blueprint(admin_bp)

    # Banco de dados: fechamento automático, tabelas e administrador inicial
    database.init_app(flask_app)
    with flask_app.app_context():
        conn = database.get_db()
        database.init_db(conn)
        user_service.ensure_default_admin(conn)

    return flask_app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=app.config["DEBUG"], host="127.0.0.1", port=5000)
