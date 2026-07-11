#!/usr/bin/env python3
"""
Ensemble Models
Combine multiple trained PredictionModel/ClassificationModel instances into
a single weighted-average (regression) or weighted-vote (classification)
predictor.
"""

import logging
from collections import Counter
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import joblib


class EnsembleModel:
    """Weighted ensemble over already-trained sub-models."""

    def __init__(self, model_type: str = "regression"):
        """model_type is 'regression' or 'classification' -- determines whether
        predict() averages or votes."""
        if model_type not in ("regression", "classification"):
            raise ValueError("model_type must be 'regression' or 'classification'")
        self.model_type = model_type
        self.logger = logging.getLogger(__name__)
        self.models: Dict[str, object] = {}
        self.weights: Dict[str, float] = {}

    def add_model(self, name: str, model, weight: float = 1.0):
        """Register a trained model (must already expose .predict())."""
        if weight <= 0:
            raise ValueError("weight must be positive")
        self.models[name] = model
        self.weights[name] = weight
        self.logger.info(f"Added ensemble member: {name} (weight={weight})")

    def remove_model(self, name: str):
        self.models.pop(name, None)
        self.weights.pop(name, None)

    def _normalized_weights(self) -> Dict[str, float]:
        total = sum(self.weights.values())
        if total == 0:
            raise ValueError("Ensemble has no members")
        return {k: v / total for k, v in self.weights.items()}

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Weighted-average predictions (regression) or weighted-vote (classification)."""
        if not self.models:
            raise ValueError("Ensemble has no members; call add_model() first")

        weights = self._normalized_weights()
        predictions = {name: np.asarray(model.predict(X)) for name, model in self.models.items()}

        if self.model_type == "regression":
            stacked = np.zeros_like(next(iter(predictions.values())), dtype=float)
            for name, preds in predictions.items():
                stacked = stacked + weights[name] * preds
            return stacked

        # Classification: weighted majority vote per sample.
        n_samples = len(next(iter(predictions.values())))
        result = []
        for i in range(n_samples):
            votes = Counter()
            for name, preds in predictions.items():
                votes[preds[i]] += weights[name]
            result.append(votes.most_common(1)[0][0])
        return np.array(result)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Weighted-average class probabilities. Requires every member to
        support predict_proba and share the same class ordering."""
        if self.model_type != "classification":
            raise ValueError("predict_proba is only available for classification ensembles")
        if not self.models:
            raise ValueError("Ensemble has no members; call add_model() first")

        weights = self._normalized_weights()
        total = None
        for name, model in self.models.items():
            if not hasattr(model, "predict_proba"):
                raise ValueError(f"Member '{name}' does not support predict_proba")
            proba = np.asarray(model.predict_proba(X))
            total = proba * weights[name] if total is None else total + proba * weights[name]
        return total

    def save_model(self, filepath: str):
        """Persist the ensemble's sub-models and weights via joblib."""
        joblib.dump({
            "model_type": self.model_type,
            "models": self.models,
            "weights": self.weights,
        }, filepath)
        self.logger.info(f"Ensemble saved to {filepath}")

    def load_model(self, filepath: str):
        data = joblib.load(filepath)
        self.model_type = data["model_type"]
        self.models = data["models"]
        self.weights = data["weights"]
        self.logger.info(f"Ensemble loaded from {filepath}")

    def members(self) -> List[Tuple[str, float]]:
        """List (name, normalized_weight) for every ensemble member."""
        weights = self._normalized_weights() if self.models else {}
        return [(name, weights[name]) for name in self.models]
