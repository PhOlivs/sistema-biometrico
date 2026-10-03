from types import SimpleNamespace

import pytest

from biometric import face_detector
from services import biometric_service


@pytest.fixture
def fake_face_pipeline(monkeypatch):
    yaw_by_frame = {"right": -0.2, "left": 0.2}
    monkeypatch.setattr(biometric_service, "is_available", lambda _config: True)
    monkeypatch.setattr(biometric_service, "_decode_frame", lambda frame: frame)
    monkeypatch.setattr(face_detector, "validate_image_quality", lambda _image: None)
    monkeypatch.setattr(
        biometric_service,
        "detect_faces",
        lambda image, _model: [SimpleNamespace(
            confidence=0.99, landmarks=image,
        )],
    )
    monkeypatch.setattr(
        biometric_service, "estimate_yaw", lambda landmarks: yaw_by_frame[landmarks]
    )
    return {"YUNET_MODEL_PATH": "yunet"}


def test_liveness_validates_the_server_issued_action_sequence(fake_face_pipeline):
    biometric_service.validate_liveness_frames(
        ["right", "left", "right"],
        challenge=["RIGHT", "LEFT", "RIGHT"],
        config=fake_face_pipeline,
    )


def test_liveness_rejects_frames_not_matching_challenge(fake_face_pipeline):
    with pytest.raises(ValueError, match="Vire o rosto"):
        biometric_service.validate_liveness_frames(
            ["left", "right", "left"],
            challenge=["RIGHT", "LEFT", "RIGHT"],
            config=fake_face_pipeline,
        )


def test_liveness_requires_one_frame_per_action(fake_face_pipeline):
    with pytest.raises(ValueError, match="cada movimento"):
        biometric_service.validate_liveness_frames(
            ["right"],
            challenge=["RIGHT", "LEFT", "RIGHT"],
            config=fake_face_pipeline,
        )


def test_failed_liveness_stops_before_sface(monkeypatch):
    monkeypatch.setattr(biometric_service, "is_available", lambda _config: True)
    monkeypatch.setattr(
        biometric_service, "validate_liveness_frames",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("liveness failed")),
    )
    sface_called = False

    def extract(*args, **kwargs):
        nonlocal sface_called
        sface_called = True
        raise AssertionError("SFace must not run before presence validation")

    monkeypatch.setattr(biometric_service, "_embedding_for_frame", extract)
    with pytest.raises(ValueError, match="liveness failed"):
        biometric_service.verify_user(
            object(), user_id=1, frame="face", liveness_frames=[],
            challenge=["RIGHT", "LEFT", "RIGHT"],
            config={"BIOMETRIC_COSINE_THRESHOLD": .363},
        )
    assert not sface_called
