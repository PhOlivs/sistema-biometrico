"""Face embedding extraction and cosine comparison using OpenCV SFace."""

from __future__ import annotations

from functools import lru_cache

from biometric.face_detector import detect_faces, validate_image_quality


@lru_cache(maxsize=1)
def _recognizer(model_path: str):
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("Instale opencv-contrib-python-headless para habilitar a biometria.") from exc
    return cv2.FaceRecognizerSF.create(model_path, "")


def extract_embedding(image, *, detector_path: str, recognizer_path: str, expected_angle: str):
    import cv2
    import numpy as np

    validate_image_quality(image)
    faces = detect_faces(image, detector_path)
    if not faces:
        raise ValueError("Nenhum rosto foi detectado. Posicione-se no centro da imagem.")
    if len(faces) != 1:
        raise ValueError("A captura deve conter somente uma pessoa.")
    face = faces[0]
    if face.confidence < 0.85:
        raise ValueError("A imagem do rosto não ficou nítida o suficiente.")
    yaw = _estimate_yaw(face.landmarks)
    if expected_angle == "FRONT" and abs(yaw) > 0.18:
        raise ValueError("Olhe diretamente para a câmera.")
    if expected_angle == "RIGHT" and yaw > -0.08:
        raise ValueError("Vire o rosto para a direita, conforme a indicação da tela.")
    if expected_angle == "LEFT" and yaw < 0.08:
        raise ValueError("Vire o rosto para a esquerda, conforme a indicação da tela.")

    aligned = _recognizer(recognizer_path).alignCrop(image, face.raw.reshape(1, -1))
    feature = _recognizer(recognizer_path).feature(aligned).reshape(-1).astype(np.float32)
    norm = float(np.linalg.norm(feature))
    if not norm:
        raise ValueError("Não foi possível obter uma representação facial válida.")
    return feature / norm


def _estimate_yaw(landmarks: tuple[float, ...]) -> float:
    right_eye_x, left_eye_x, nose_x = landmarks[0], landmarks[2], landmarks[4]
    eye_distance = abs(left_eye_x - right_eye_x)
    if eye_distance < 1:
        raise ValueError("Não foi possível validar a posição do rosto.")
    eye_midpoint = (right_eye_x + left_eye_x) / 2
    return (nose_x - eye_midpoint) / eye_distance


def cosine_similarity(first: np.ndarray, second: np.ndarray) -> float:
    import numpy as np

    first = np.asarray(first, dtype=np.float32).reshape(-1)
    second = np.asarray(second, dtype=np.float32).reshape(-1)
    if first.shape != second.shape:
        raise ValueError("Os modelos biométricos possuem formatos incompatíveis.")
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if not denominator:
        return -1.0
    return float(np.dot(first, second) / denominator)
