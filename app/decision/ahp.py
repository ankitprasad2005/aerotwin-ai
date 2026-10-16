"""Analytic Hierarchy Process (Saaty): factor weights from pairwise importance judgements.

Each judgement (a, b): v says factor a is v times as important as factor b on Saaty's 1-9 scale. The
weights are the principal eigenvector of the reciprocal comparison matrix, and the consistency ratio
(CR) measures how far the judgements contradict each other; CR < 0.1 is the usual acceptance limit.
"""
from collections.abc import Mapping, Sequence

# Saaty's random consistency index by matrix size.
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}

# The default decision-factor judgements (Saaty scale). Feasibility is not judged: every failed check is a
# conflict that already forces REJECT, so for any decision that is not rejected feasibility is always 1.
FACTOR_JUDGEMENTS: dict[tuple[str, str], float] = {
    ("profit", "confidence"): 2,      # the money is the reason to make the change at all
    ("profit", "risk"): 2,
    ("profit", "data_quality"): 3,
    ("confidence", "risk"): 1,        # the agents' certainty and the warnings they raise matter equally
    ("confidence", "data_quality"): 2,
    ("risk", "data_quality"): 2,      # evidence quality refines the picture but is incomplete (no DGCA data yet)
}


def _matrix(names: Sequence[str], judgements: Mapping[tuple[str, str], float]) -> list[list[float]]:
    index = {name: i for i, name in enumerate(names)}
    matrix = [[1.0] * len(names) for _ in names]
    for (a, b), value in judgements.items():
        matrix[index[a]][index[b]] = float(value)
        matrix[index[b]][index[a]] = 1.0 / value
    return matrix


def _principal(matrix: list[list[float]]) -> tuple[list[float], float]:
    n = len(matrix)
    weights = [1.0 / n] * n
    for _ in range(200):
        product = [sum(matrix[i][j] * weights[j] for j in range(n)) for i in range(n)]
        total = sum(product)
        weights = [value / total for value in product]
    lambda_max = sum(sum(matrix[i][j] * weights[j] for j in range(n)) / weights[i] for i in range(n)) / n
    return weights, lambda_max


def ahp_weights(names: Sequence[str], judgements: Mapping[tuple[str, str], float]) -> dict[str, float]:
    weights, _ = _principal(_matrix(names, judgements))
    return dict(zip(names, weights))


def consistency_ratio(names: Sequence[str], judgements: Mapping[tuple[str, str], float]) -> float:
    n = len(names)
    if n < 3:
        return 0.0
    _, lambda_max = _principal(_matrix(names, judgements))
    return ((lambda_max - n) / (n - 1)) / RANDOM_INDEX[n]
