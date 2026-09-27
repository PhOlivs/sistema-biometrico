import os

# Diretório raiz do projeto (um nível acima de config/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    # Nome e subtítulo do sistema, usados no frontend (index.html, etc.)
    SYSTEM_NAME = "Protocolo Égide"
    SYSTEM_SUBTITLE = "Contenção primária contra dados de toxinas e risco de catástrofe global."

    # Chave secreta do Flask (sessões, flash messages).
    # Em desenvolvimento, usa-se um valor padrão fixo; em um ambiente
    # real, isso viria obrigatoriamente de variável de ambiente.
    SECRET_KEY = os.environ.get("EGIDE_SECRET_KEY", "dev-secret-key-fase1")

    # Modo de desenvolvimento (ativa reload automático e mensagens de debug)
    DEBUG = True

    # Caminhos que serão utilizados a partir da Fase 4/6 em diante
    DATABASE_PATH = os.path.join(BASE_DIR, "database", "egide.db")
    FACES_DIR = os.path.join(BASE_DIR, "data", "faces")
