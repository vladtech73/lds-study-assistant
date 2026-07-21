"""Golden-question evaluation harness (PR4)."""

from lds_study.eval.golden import GoldenQuestion, load_golden_set
from lds_study.eval.metrics import AggregateMetrics, ItemMetrics, aggregate
from lds_study.eval.run import EvalResult, run_eval

__all__ = [
    "AggregateMetrics",
    "EvalResult",
    "GoldenQuestion",
    "ItemMetrics",
    "aggregate",
    "load_golden_set",
    "run_eval",
]
