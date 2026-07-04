"""Evaluation harness for per-instance detection scoring."""

from .evaluate import Alert, DetectionResult, evaluate_per_instance, summarize_evaluation, confusion_matrix_per_flavor

__all__ = [
    'Alert',
    'DetectionResult',
    'evaluate_per_instance',
    'summarize_evaluation',
    'confusion_matrix_per_flavor',
]
