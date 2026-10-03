"""Enrollment and verification of encrypted facial templates."""

import base64
import binascii
import os
import secrets

from biometric.face_recognizer import (
    cosine_similarity, estimate_yaw, extract_embedding, validate_face_orientation,
)
from biometric.face_detector import detect_faces
from services import auth_service
from services.user_service import now_iso

MAX_IMAGE_BYTES = 3 * 1024 * 1024
REQUIRED_ANGLES = ("FRONT", "RIGHT", "LEFT")
LIVENESS_ACTIONS = ("RIGHT", "LEFT")
LIVENESS_ACTION_COUNT = 3


def create_liveness_challenge() -> list[str]:
    return [secrets.choice(LIVENESS_ACTIONS) for _ in range(LIVENESS_ACTION_COUNT)]


def validate_liveness_frames(frames, *, challenge, config) -> None:
    if not is_available(config):
        raise RuntimeError(
            "Modelos biométricos ausentes. Configure YuNet e SFace conforme a documentação."
        )
    if (
        not isinstance(challenge, list)
        or len(challenge) != LIVENESS_ACTION_COUNT
        or any(action not in LIVENESS_ACTIONS for action in challenge)
    ):
        raise ValueError("Desafio de presença inválido ou expirado. Tente novamente.")
    if not isinstance(frames, list) or len(frames) != len(challenge):
        raise ValueError("Complete cada movimento solicitado para confirmar sua presença.")

    for frame_data, expected_action in zip(frames, challenge):
        image = _decode_frame(frame_data)
        from biometric.face_detector import validate_image_quality

        validate_image_quality(image)
        faces = detect_faces(image, config["YUNET_MODEL_PATH"])
        if len(faces) != 1:
            raise ValueError("Cada movimento deve mostrar somente um rosto.")
        face = faces[0]
        if face.confidence < 0.85:
            raise ValueError("Não foi possível validar um dos movimentos. Tente novamente.")
        validate_face_orientation(estimate_yaw(face.landmarks), expected_action)


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


def _profile_photo_for_frame(frame, config) -> bytes:
    import cv2

    image = _decode_frame(frame)
    faces = detect_faces(image, config["YUNET_MODEL_PATH"])
    if len(faces) != 1:
        raise ValueError("A foto do perfil precisa conter exatamente um rosto.")
    height, width = image.shape[:2]
    x, y, face_width, face_height = faces[0].box
    margin_x = int(face_width * 0.3)
    margin_y = int(face_height * 0.3)
    left = max(0, x - margin_x)
    top = max(0, y - margin_y)
    right = min(width, x + face_width + margin_x)
    bottom = min(height, y + face_height + margin_y)
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        raise ValueError("Não foi possível preparar a foto do perfil.")
    thumbnail = cv2.resize(crop, (360, 360), interpolation=cv2.INTER_AREA)
    success, encoded = cv2.imencode(".jpg", thumbnail, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not success:
        raise RuntimeError("Não foi possível preparar a foto do perfil.")
    return encoded.tobytes()


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
    photo = _profile_photo_for_frame(frames["FRONT"], config)
    protected_photo = auth_service.encrypt_sensitive(
        base64.b64encode(photo).decode("ascii")
    )
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM biometric_profiles WHERE user_id = ?", (user_id,))
        conn.execute(
            "UPDATE users SET profile_photo_encrypted = ?, updated_at = ? WHERE id = ?",
            (protected_photo.encode("ascii"), now_iso(), user_id),
        )
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


def verify_user(
    conn, *, user_id: int, frame: str, liveness_frames, challenge, config
) -> tuple[bool, dict[str, float]]:
    import numpy as np

    if not is_available(config):
        raise RuntimeError(
            "Modelos biométricos ausentes. Configure YuNet e SFace conforme a documentação."
        )
    validate_liveness_frames(liveness_frames, challenge=challenge, config=config)
    candidate = _embedding_for_frame(frame, "FRONT", config)
    rows = conn.execute(
        "SELECT angle, embedding FROM biometric_profiles WHERE user_id = ?", (user_id,)
    ).fetchall()
    if len(rows) != len(REQUIRED_ANGLES) or {row["angle"] for row in rows} != set(REQUIRED_ANGLES):
        return False, {}
    similarities = {}
    for row in rows:
        encoded = auth_service.decrypt_sensitive(bytes(row["embedding"]).decode("ascii"))
        stored = np.frombuffer(base64.b64decode(encoded), dtype=np.float32)
        similarities[row["angle"]] = cosine_similarity(candidate, stored)
    best = max(similarities.values())
    threshold = float(config["BIOMETRIC_COSINE_THRESHOLD"])
    scores = similarities | {"MAX": best, "THRESHOLD": threshold}
    return best >= threshold, scores
