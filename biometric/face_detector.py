"""Face detection and basic frame quality checks using OpenCV YuNet."""

from dataclasses import dataclass
from functools import lru_cache


def _cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("Instale opencv-contrib-python-headless para habilitar a biometria.") from exc
    return cv2


@dataclass
class DetectedFace:
    box: tuple[int, int, int, int]
    landmarks: tuple[float, ...]
    confidence: float
    raw: object


@lru_cache(maxsize=1)
def _detector(model_path: str):
    cv2 = _cv2()
    detector = cv2.FaceDetectorYN.create(
        model_path, "", (320, 320), 0.85, 0.3, 5000
    )
    return detector


def detect_faces(image, model_path: str) -> list[DetectedFace]:
    height, width = image.shape[:2]
    detector = _detector(model_path)
    detector.setInputSize((width, height))
    _, faces = detector.detect(image)
    if faces is None:
        return []
    return [
        DetectedFace(
            box=tuple(int(value) for value in face[:4]),
            landmarks=tuple(float(value) for value in face[4:14]),
            confidence=float(face[14]),
            raw=face,
        )
        for face in faces
    ]


def validate_image_quality(image) -> None:
    cv2 = _cv2()
    height, width = image.shape[:2]
    if width < 320 or height < 240:
        raise ValueError("A imagem está pequena. Aproxime-se e tente novamente.")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    if brightness < 35:
        raise ValueError("A imagem está escura. Melhore a iluminação e tente novamente.")
    if brightness > 225:
        raise ValueError("A imagem está muito clara. Reduza a luz direta e tente novamente.")
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if sharpness < 25:
        raise ValueError("A imagem está desfocada. Mantenha o rosto imóvel e tente novamente.")
