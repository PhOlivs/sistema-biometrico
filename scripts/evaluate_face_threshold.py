"""Evaluate FAR/FRR/EER from a CSV containing labeled face similarity scores."""

import argparse
import csv
import sys

from services.biometric_metrics import evaluate_thresholds, threshold_metrics


def read_scores(path: str) -> tuple[list[float], list[float]]:
    genuine = []
    impostor = []
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames or not {"pair_type", "score"} <= set(reader.fieldnames):
            raise ValueError("O CSV precisa ter as colunas pair_type e score.")
        for line, row in enumerate(reader, start=2):
            pair_type = (row["pair_type"] or "").strip().lower()
            if pair_type not in ("genuine", "impostor"):
                raise ValueError(f"Linha {line}: pair_type deve ser genuine ou impostor.")
            try:
                score = float(row["score"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Linha {line}: score precisa ser numérico.") from exc
            (genuine if pair_type == "genuine" else impostor).append(score)
    return genuine, impostor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", help="CSV local com pair_type,score")
    parser.add_argument(
        "--threshold", type=float, default=0.363,
        help="Threshold que deseja avaliar (padrão: 0.363)",
    )
    args = parser.parse_args()

    try:
        genuine, impostor = read_scores(args.csv_path)
        current = threshold_metrics(genuine, impostor, args.threshold)
        _curve, eer = evaluate_thresholds(genuine, impostor)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"Pares genuínos: {len(genuine)}")
    print(f"Pares impostores: {len(impostor)}")
    print(
        f"Threshold {current['threshold']:.3f}: "
        f"FAR={current['far']:.2%} FRR={current['frr']:.2%}"
    )
    print(
        f"EER aproximado: {eer['eer']:.2%} "
        f"no threshold {eer['threshold']:.6f} "
        f"(FAR={eer['far']:.2%}, FRR={eer['frr']:.2%}, "
        f"diferença={eer['eer_gap']:.2%})"
    )
    print("EER é uma estimativa discreta do ponto de equilíbrio; não é uma certificação.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
