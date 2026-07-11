#!/usr/bin/env python3
"""
ML Optimizer
Hyperparameter tuning for PredictionModel/ClassificationModel-style
estimators, via scikit-learn's GridSearchCV/RandomizedSearchCV.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

try:
    from sklearn.model_selection import GridSearchCV, RandomizedSearchCV
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("Scikit-learn not available. Install with: pip install scikit-learn")


@dataclass
class OptimizationResult:
    """Result of a hyperparameter search, mirroring ModelResult's shape."""
    best_params: Dict[str, Any]
    best_score: float
    scoring: str
    cv_results: Dict[str, Any] = field(default_factory=dict)
    search_time: float = 0.0


class MLOptimizer:
    """Hyperparameter search over a PredictionModel/ClassificationModel's
    underlying sklearn estimator."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if not SKLEARN_AVAILABLE:
            raise ImportError("Scikit-learn is required for MLOptimizer")

    def _prepare(self, model, X: pd.DataFrame):
        """Return a raw sklearn estimator to tune, plus (optionally) scaled X.

        Accepts either a raw sklearn estimator, or a PredictionModel/
        ClassificationModel wrapper -- trained or not. An untrained wrapper's
        `.model` is None, so a fresh estimator is built via its
        `_create_model()` so the search has something to fit.
        """
        is_wrapper = hasattr(model, "_create_model") and hasattr(model, "model_type")
        if is_wrapper:
            estimator = model.model if model.model is not None else model._create_model(model.model_type)
        else:
            estimator = model  # already a raw sklearn estimator

        X_input = X
        scaler = getattr(model, "scaler", None)
        if scaler is not None:
            X_input = scaler.transform(X)
        elif is_wrapper and getattr(model, "model", None) is None:
            # Untrained wrapper: mirror ModelConfig's scale_features=True default
            # (used by PredictionModel/ClassificationModel.train()) so the search
            # scores the estimator under the same conditions it will actually run in.
            X_input = StandardScaler().fit_transform(X)
        return estimator, X_input

    def grid_search(self, model, param_grid: Dict[str, List[Any]],
                    X: pd.DataFrame, y: pd.Series, cv: int = 5,
                    scoring: Optional[str] = None) -> OptimizationResult:
        """Exhaustive grid search over param_grid.

        `model` is a PredictionModel/ClassificationModel wrapper (its
        `.model` attribute is the sklearn estimator being tuned) or a raw
        sklearn estimator.
        """
        import time
        estimator, X_input = self._prepare(model, X)
        start = time.time()

        search = GridSearchCV(estimator, param_grid, cv=cv, scoring=scoring)
        search.fit(X_input, y)

        return OptimizationResult(
            best_params=search.best_params_, best_score=search.best_score_,
            scoring=scoring or "default", cv_results=dict(search.cv_results_),
            search_time=time.time() - start,
        )

    def random_search(self, model, param_distributions: Dict[str, Any],
                      X: pd.DataFrame, y: pd.Series, n_iter: int = 20,
                      cv: int = 5, scoring: Optional[str] = None,
                      random_state: int = 42) -> OptimizationResult:
        """Randomized search over param_distributions -- cheaper than grid
        search for large hyperparameter spaces."""
        import time
        estimator, X_input = self._prepare(model, X)
        start = time.time()

        search = RandomizedSearchCV(
            estimator, param_distributions, n_iter=n_iter, cv=cv,
            scoring=scoring, random_state=random_state,
        )
        search.fit(X_input, y)

        return OptimizationResult(
            best_params=search.best_params_, best_score=search.best_score_,
            scoring=scoring or "default", cv_results=dict(search.cv_results_),
            search_time=time.time() - start,
        )
