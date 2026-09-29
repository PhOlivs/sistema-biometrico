import os

# Diretório raiz do projeto (um nível acima de config/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    SYSTEM_NAME = "Protocolo Égide"
    SYSTEM_SUBTITLE = "Sistema acadêmico de identificação biométrica e controle de acesso."
    SECRET_KEY = os.environ.get("EGIDE_SECRET_KEY", "desenvolvimento-local-nao-utilizar-em-producao")
    DATA_ENCRYPTION_KEY = os.environ.get("EGIDE_DATA_ENCRYPTION_KEY")
    DEBUG = os.environ.get("EGIDE_DEBUG", "1") == "1"
    DATABASE_PATH = os.path.join(BASE_DIR, "database", "egide.db")
    MODELS_DIR = os.path.join(BASE_DIR, "data", "models")
    YUNET_MODEL_PATH = os.environ.get(
        "EGIDE_YUNET_MODEL", os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
    )
    SFACE_MODEL_PATH = os.environ.get(
        "EGIDE_SFACE_MODEL", os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")
    )
    BIOMETRIC_MODEL_VERSION = "opencv-yunet-sface-2023"
    BIOMETRIC_COSINE_THRESHOLD = float(os.environ.get("EGIDE_FACE_THRESHOLD", "0.363"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = not DEBUG
    PERMANENT_SESSION_LIFETIME = 1800
