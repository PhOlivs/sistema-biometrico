import pytest

from services.biometric_metrics import evaluate_thresholds, threshold_metrics


def test_threshold_metrics_count_false_accepts_and_rejects():
    metrics = threshold_metrics(
        genuine_scores=[0.8, 0.6, 0.3],
        impostor_scores=[0.7, 0.2],
        threshold=0.65,
    )
    assert metrics["far"] == 0.5
    assert metrics["frr"] == pytest.approx(2 / 3)


def test_eer_estimate_uses_both_labeled_score_groups():
    curve, eer = evaluate_thresholds(
        genuine_scores=[0.8, 0.9, 0.7],
        impostor_scores=[0.2, 0.4, 0.6],
    )
    assert curve
    assert eer["threshold"] in {row["threshold"] for row in curve}
    assert eer["eer_gap"] == 0


@pytest.mark.parametrize(
    "genuine,impostor,threshold",
    [([], [0.1], 0.3), ([0.9], [], 0.3), ([0.9], [0.1], 1.1)],
)
def test_threshold_metrics_reject_invalid_samples(genuine, impostor, threshold):
    with pytest.raises(ValueError):
        threshold_metrics(genuine, impostor, threshold)
