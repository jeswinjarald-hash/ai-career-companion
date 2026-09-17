import pytest

from app.services.m2_4_evaluation import _ndcg, calculate_retrieval_metrics


def test_ndcg_perfect_primary_order() -> None:
    assert _ndcg(["A", "B", "C"], {"A", "B"}, {"C"}, 3) == 1.0


def test_ndcg_penalizes_irrelevant_first_result() -> None:
    score = _ndcg(["X", "A", "C"], {"A"}, {"C"}, 3)

    assert 0 < score < 1


def test_domain_metrics_support_empty_expectations() -> None:
    assert _ndcg(["X"], set(), set(), 1) == 0.0


def test_retrieval_metrics_hand_calculation() -> None:
    metrics = calculate_retrieval_metrics(["wrong", "primary", "secondary"], ["primary"], ["secondary"], 3)

    assert metrics["hit_rate"] == 1.0
    assert metrics["strict_precision"] == pytest.approx(1 / 3)
    assert metrics["relaxed_precision"] == pytest.approx(2 / 3)
    assert metrics["domain_recall"] == 1.0
    assert metrics["reciprocal_rank"] == pytest.approx(1 / 2)


def test_retrieval_metrics_reject_invalid_k() -> None:
    with pytest.raises(ValueError):
        calculate_retrieval_metrics(["primary"], ["primary"], [], 2)
