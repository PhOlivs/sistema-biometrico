"""Enrollment and verification of encrypted facial templates."""

import base64
import binascii
import os

from biometric.face_recognizer import cosine_similarity, extract_embedding
from services import auth_service
from services.user_service import now_iso

MAX_IMAGE_BYTES = 3 * 1024 * 1024
REQUIRED_ANGLES = ("FRONT", "RIGHT", "LEFT")


def is_available(config) -> bool:
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    return os.path.isfile(config["YUNET_MODEL_PATH"]) and os.path.isfile(
        config["SFACE_MODEL_PATH"]
    )


def _decode_frame(data):
    import cv2
    import numpy as np

    if not isinstance(data, str):
        raise ValueError("Uma captura está ausente ou inválida.")
    encoded = data.split(",", 1)[1] if data.startswith("data:image/") else data
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("A captura recebida não é uma imagem válida.") from exc
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("A imagem deve ter no máximo 3 MB.")
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Não foi possível ler a imagem capturada.")
    return image


def _embedding_for_frame(frame, angle: str, config):
    image = _decode_frame(frame)
    return extract_embedding(
        image,
        detector_path=config["YUNET_MODEL_PATH"],
        recognizer_path=config["SFACE_MODEL_PATH"],
        expected_angle=angle,
    )


def enroll_user(conn, *, user_id: int, frames: dict, config) -> None:
    import numpy as np

    if not isinstance(frames, dict) or set(frames) != set(REQUIRED_ANGLES):
        raise ValueError("As capturas frontal, direita e esquerda são obrigatórias.")
    if not is_available(config):
        raise RuntimeError(
            "Modelos biométricos ausentes. Configure YuNet e SFace conforme a documentação."
        )
    templates = {
        angle: _embedding_for_frame(frames[angle], angle, config)
        for angle in REQUIRED_ANGLES
    }
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM biometric_profiles WHERE user_id = ?", (user_id,))
        for angle, template in templates.items():
            protected = auth_service.encrypt_sensitive(
                base64.b64encode(template.astype(np.float32).tobytes()).decode("ascii")
            )
            conn.execute(
                """
                INSERT INTO biometric_profiles (user_id, angle, embedding, model_version, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id, angle, protected.encode("ascii"),
                    config["BIOMETRIC_MODEL_VERSION"], now_iso(),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def verify_user(conn, *, user_id: int, frame: str, config) -> tuple[bool, float | None]:
    import numpy as np

    if not is_available(config):
        raise RuntimeError(
            "Modelos biométricos ausentes. Configure YuNet e SFace conforme a documentação."
        )
    candidate = _embedding_for_frame(frame, "FRONT", config)
    rows = conn.execute(
        "SELECT embedding FROM biometric_profiles WHERE user_id = ?", (user_id,)
    ).fetchall()
    if len(rows) != 3:
        return False, None
    similarities = []
    for row in rows:
        encoded = auth_service.decrypt_sensitive(bytes(row["embedding"]).decode("ascii"))
        stored = np.frombuffer(base64.b64decode(encoded), dtype=np.float32)
        similarities.append(cosine_similarity(candidate, stored))
    best = max(similarities)
    return best >= config["BIOMETRIC_COSINE_THRESHOLD"], best
