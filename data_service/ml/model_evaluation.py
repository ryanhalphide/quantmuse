#!/usr/bin/env python3
"""
Model Evaluation
Extended evaluation metrics for trained PredictionModel/ClassificationModel
instances, built purely on scikit-learn -- no new dependencies.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

try:
    from sklearn.metrics import (
        r2_score, mean_squared_error, mean_absolute_error,
        accuracy_score, precision_score, recall_score, f1_score,
        confusion_matrix, roc_auc_score, roc_curve, precision_recall_curve,
    )
    from sklearn.model_selection import learning_curve as sk_learning_curve
    from sklearn.inspection import permutation_importance as sk_permutation_importance
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("Scikit-learn not available. Install with: pip install scikit-learn")


@dataclass
class EvaluationReport:
    """Extended evaluation metrics for a trained model."""
    model_type: str  # 'regression' or 'classification'
    metrics: Dict[str, float] = field(default_factory=dict)
    confusion: Optional[np.ndarray] = None
    roc_curve: Optional[Dict[str, np.ndarray]] = None
    precision_recall_curve: Optional[Dict[str, np.ndarray]] = None
    residuals: Optional[np.ndarray] = None


class ModelEvaluator:
    """Compute richer evaluation metrics than MLModelManager's basic scores."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if not SKLEARN_AVAILABLE:
            raise ImportError("Scikit-learn is required for ModelEvaluator")

    def evaluate(self, model, X_test: pd.DataFrame, y_test: pd.Series,
                model_type: str = "regression") -> EvaluationReport:
        """Evaluate a trained PredictionModel/ClassificationModel on held-out data.

        model_type is 'regression' or 'classification'.
        """
        predictions = model.predict(X_test)

        if model_type == "regression":
            residuals = y_test.values - predictions
            metrics = {
                "r2": r2_score(y_test, predictions),
                "mse": mean_squared_error(y_test, predictions),
                "rmse": mean_squared_error(y_test, predictions) ** 0.5,
                "mae": mean_absolute_error(y_test, predictions),
            }
            return EvaluationReport(model_type=model_type, metrics=metrics,
                                    residuals=residuals)

        if model_type == "classification":
            metrics = {
                "accuracy": accuracy_score(y_test, predictions),
                "precision": precision_score(y_test, predictions, average="weighted",
                                            zero_division=0),
                "recall": recall_score(y_test, predictions, average="weighted",
                                      zero_division=0),
                "f1": f1_score(y_test, predictions, average="weighted", zero_division=0),
            }
            confusion = confusion_matrix(y_test, predictions)

            roc = None
            pr = None
            binary = len(set(y_test)) == 2
            if binary and hasattr(model, "predict_proba"):
                try:
                    proba = model.predict_proba(X_test)[:, 1]
                    metrics["roc_auc"] = roc_auc_score(y_test, proba)
                    fpr, tpr, thresholds = roc_curve(y_test, proba)
                    roc = {"fpr": fpr, "tpr": tpr, "thresholds": thresholds}
                    prec, rec, pr_thresholds = precision_recall_curve(y_test, proba)
                    pr = {"precision": prec, "recall": rec, "thresholds": pr_thresholds}
                except Exception as e:
                    self.logger.warning(f"Could not compute ROC/PR curves: {e}")

            return EvaluationReport(model_type=model_type, metrics=metrics,
                                    confusion=confusion, roc_curve=roc,
                                    precision_recall_curve=pr)

        raise ValueError(f"Unknown model_type: {model_type}")

    def learning_curve(self, model, X: pd.DataFrame, y: pd.Series,
                       cv: int = 5, train_sizes: Optional[List[float]] = None
                       ) -> Dict[str, np.ndarray]:
        """Compute train/validation score vs. training-set size.

        `model` must expose the raw sklearn estimator as `.model` (as
        PredictionModel/ClassificationModel do) so scikit-learn's cross-
        validation machinery can refit it directly.
        """
        estimator = getattr(model, "model", model)
        train_sizes = train_sizes or [0.1, 0.325, 0.55, 0.775, 1.0]

        X_input = model.scaler.transform(X) if getattr(model, "scaler", None) else X
        sizes, train_scores, val_scores = sk_learning_curve(
            estimator, X_input, y, cv=cv, train_sizes=train_sizes,
        )
        return {
            "train_sizes": sizes,
            "train_scores_mean": train_scores.mean(axis=1),
            "train_scores_std": train_scores.std(axis=1),
            "val_scores_mean": val_scores.mean(axis=1),
            "val_scores_std": val_scores.std(axis=1),
        }

    def permutation_importance(self, model, X: pd.DataFrame, y: pd.Series,
                               n_repeats: int = 10, random_state: int = 42
                               ) -> Dict[str, float]:
        """Feature importance via permutation, robust across model types
        (unlike `.feature_importances_`, works for any estimator)."""
        estimator = getattr(model, "model", model)
        X_input = model.scaler.transform(X) if getattr(model, "scaler", None) else X

        result = sk_permutation_importance(
            estimator, X_input, y, n_repeats=n_repeats, random_state=random_state,
        )
        return dict(zip(X.columns, result.importances_mean))
