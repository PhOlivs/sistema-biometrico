"""Empirical face-threshold evaluation from labeled similarity scores."""

import math


def threshold_metrics(genuine_scores, impostor_scores, threshold: float) -> dict[str, float]:
    genuine = list(genuine_scores)
    impostor = list(impostor_scores)
    if not genuine or not impostor:
        raise ValueError("São necessários scores genuínos e impostores.")
    if not all(
        math.isfinite(score) and -1.0 <= score <= 1.0
        for score in genuine + impostor
    ):
        raise ValueError("Os scores de similaridade do cosseno devem estar entre -1 e 1.")
    if not math.isfinite(threshold) or not -1.0 <= threshold <= 1.0:
        raise ValueError("O threshold deve estar entre -1 e 1.")
    false_accepts = sum(score >= threshold for score in impostor)
    false_rejects = sum(score < threshold for score in genuine)
    far = false_accepts / len(impostor)
    frr = false_rejects / len(genuine)
    return {
        "threshold": float(threshold),
        "far": far,
        "frr": frr,
        "eer_gap": abs(far - frr),
    }


def evaluate_thresholds(genuine_scores, impostor_scores) -> tuple[list[dict[str, float]], dict[str, float]]:
    genuine = list(genuine_scores)
    impostor = list(impostor_scores)
    if not genuine or not impostor:
        raise ValueError("São necessários scores genuínos e impostores.")
    candidates = sorted({-1.0, 1.0, *genuine, *impostor})
    metrics = [
        threshold_metrics(genuine, impostor, threshold)
        for threshold in candidates
    ]
    eer_estimate = min(metrics, key=lambda row: row["eer_gap"])
    eer_estimate = eer_estimate | {
        "eer": (eer_estimate["far"] + eer_estimate["frr"]) / 2
    }
    return metrics, eer_estimate
