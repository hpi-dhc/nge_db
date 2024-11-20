"""Module containing useful functions in the significance classification context."""

from typing import Any, Sequence

import numpy as np
import wandb
from sklearn.metrics import classification_report


def log_metrics_to_wandb(
    y_true_num: Sequence[int],
    y_pred_proba: np.ndarray,
    id2label: dict[int, str],
    labels: list[str],
    run: Any,
) -> None:
    """Log binary classification metrics to Weights&Biases."""
    y_pred_num = np.argmax(y_pred_proba, axis=1)
    y_true_str = [id2label[e] for e in y_true_num]
    y_pred_str = [id2label[e] for e in y_pred_num]
    # Confusion Matrix
    cm = wandb.plot.confusion_matrix(
        y_true=y_true_num, preds=y_pred_num, class_names=labels
    )
    wandb.log({"test_cm": cm})
    # PR-Curve
    wandb.log({"test_pr": wandb.plot.pr_curve(y_true_num, y_pred_proba, labels)})
    # ROC Curve
    wandb.log({"test_roc": wandb.plot.roc_curve(y_true_num, y_pred_proba, labels)})
    # Log predicted probabilities
    wandb.log(
        {
            "test_probas": wandb.Table(
                data=y_pred_proba, columns=["prob_significant", "prob_not_significant"]
            )
        }
    )
    # Additional Metrics
    report = classification_report(
        y_pred=y_pred_str, y_true=y_true_str, output_dict=True
    )
    wandb.log({"test": report})
    # Ensure summary metrics are present
    run.summary.update({"test": report})
    run.finish()
