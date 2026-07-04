#!/usr/bin/env python3
"""
Deep Learning Models
Neural network models (MLP, LSTM) for prediction/classification, with a
sklearn-compatible interface (train/predict/predict_proba/save_model/
load_model) matching PredictionModel/ClassificationModel so they drop into
MLModelManager and the rest of the ML pipeline unchanged.

Requires torch (part of the `ai` extra: pip install -e ".[ai]").
"""

import logging
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import r2_score, accuracy_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import TensorDataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from .ml_models import ModelConfig, ModelResult


class _MLPNet(nn.Module if TORCH_AVAILABLE else object):
    """Simple feed-forward network for tabular data."""

    def __init__(self, n_features: int, hidden_size: int, num_layers: int, n_outputs: int):
        super().__init__()
        layers = []
        in_dim = n_features
        for _ in range(num_layers):
            layers += [nn.Linear(in_dim, hidden_size), nn.ReLU()]
            in_dim = hidden_size
        layers.append(nn.Linear(in_dim, n_outputs))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


class _LSTMNet(nn.Module if TORCH_AVAILABLE else object):
    """LSTM over a sliding window of past rows, for sequence-aware prediction."""

    def __init__(self, n_features: int, hidden_size: int, num_layers: int, n_outputs: int):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden_size, num_layers, batch_first=True)
        self.head = nn.Linear(hidden_size, n_outputs)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :])  # last timestep


class DeepLearningModel:
    """MLP or LSTM model with the same train/predict/save/load interface as
    PredictionModel/ClassificationModel.
    """

    def __init__(self, architecture: str = "mlp", task: str = "regression",
                 hidden_size: int = 64, num_layers: int = 2,
                 sequence_length: int = 10, epochs: int = 50,
                 learning_rate: float = 1e-3, batch_size: int = 32):
        if not TORCH_AVAILABLE:
            raise ImportError(
                "torch is required for DeepLearningModel. "
                "Install with: pip install -e '.[ai]' (or pip install torch)"
            )
        if not SKLEARN_AVAILABLE:
            raise ImportError("Scikit-learn is required for DeepLearningModel")
        if architecture not in ("mlp", "lstm"):
            raise ValueError("architecture must be 'mlp' or 'lstm'")
        if task not in ("regression", "classification"):
            raise ValueError("task must be 'regression' or 'classification'")

        self.architecture = architecture
        self.task = task
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.sequence_length = sequence_length
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.batch_size = batch_size

        self.model: Optional[nn.Module] = None
        self.scaler: Optional[StandardScaler] = None
        self.n_classes: Optional[int] = None
        self.logger = logging.getLogger(__name__)

    def _make_sequences(self, X: np.ndarray, y: Optional[np.ndarray] = None):
        """Slide a window of `sequence_length` rows across X (assumes X is
        already time-ordered). Aligns y to the window's last row."""
        n = len(X)
        if n <= self.sequence_length:
            raise ValueError(
                f"Need more than sequence_length={self.sequence_length} rows; got {n}"
            )
        sequences = np.stack([X[i:i + self.sequence_length] for i in range(n - self.sequence_length)])
        if y is not None:
            aligned_y = y[self.sequence_length:]
            return sequences, aligned_y
        return sequences

    def _build_network(self, n_features: int, n_outputs: int) -> nn.Module:
        if self.architecture == "mlp":
            return _MLPNet(n_features, self.hidden_size, self.num_layers, n_outputs)
        return _LSTMNet(n_features, self.hidden_size, self.num_layers, n_outputs)

    def train(self, X: pd.DataFrame, y: pd.Series,
             config: Optional[ModelConfig] = None) -> ModelResult:
        """Train the network. Returns a ModelResult matching
        PredictionModel/ClassificationModel's shape."""
        start_time = datetime.now()
        test_size = config.test_size if config else 0.2
        random_state = config.random_state if config else 42
        scale = config.scale_features if config else True

        X_train_raw, X_test_raw, y_train_raw, y_test_raw = train_test_split(
            X.values, y.values, test_size=test_size, random_state=random_state,
            stratify=y.values if self.task == "classification" else None,
        )

        if scale:
            self.scaler = StandardScaler()
            X_train_raw = self.scaler.fit_transform(X_train_raw)
            X_test_raw = self.scaler.transform(X_test_raw)

        if self.task == "classification":
            self.n_classes = len(np.unique(y.values))
            n_outputs = self.n_classes
            y_train_raw = y_train_raw.astype(np.int64)
            y_test_raw = y_test_raw.astype(np.int64)
        else:
            n_outputs = 1

        if self.architecture == "lstm":
            X_train_raw, y_train_raw = self._make_sequences(X_train_raw, y_train_raw)
            X_test_raw, y_test_raw = self._make_sequences(X_test_raw, y_test_raw)
            n_features = X_train_raw.shape[-1]
        else:
            n_features = X_train_raw.shape[-1]

        self.model = self._build_network(n_features, n_outputs)

        X_train_t = torch.tensor(X_train_raw, dtype=torch.float32)
        X_test_t = torch.tensor(X_test_raw, dtype=torch.float32)
        if self.task == "classification":
            y_train_t = torch.tensor(y_train_raw, dtype=torch.long)
            y_test_t = torch.tensor(y_test_raw, dtype=torch.long)
            criterion = nn.CrossEntropyLoss()
        else:
            y_train_t = torch.tensor(y_train_raw, dtype=torch.float32).view(-1, 1)
            y_test_t = torch.tensor(y_test_raw, dtype=torch.float32).view(-1, 1)
            criterion = nn.MSELoss()

        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.learning_rate)
        loader = DataLoader(TensorDataset(X_train_t, y_train_t),
                           batch_size=self.batch_size, shuffle=True)

        self.model.train()
        for _ in range(self.epochs):
            for xb, yb in loader:
                optimizer.zero_grad()
                loss = criterion(self.model(xb), yb)
                loss.backward()
                optimizer.step()

        self.model.eval()
        with torch.no_grad():
            train_pred = self.model(X_train_t)
            test_pred = self.model(X_test_t)

        if self.task == "classification":
            train_labels = train_pred.argmax(dim=1).numpy()
            test_labels = test_pred.argmax(dim=1).numpy()
            train_score = accuracy_score(y_train_raw, train_labels)
            test_score = accuracy_score(y_test_raw, test_labels)
            model_name = f"{self.architecture}_classifier"
            model_type = "classification"
            predictions = test_labels
        else:
            train_score = r2_score(y_train_raw, train_pred.numpy().flatten())
            test_score = r2_score(y_test_raw, test_pred.numpy().flatten())
            model_name = f"{self.architecture}_regressor"
            model_type = "regression"
            predictions = test_pred.numpy().flatten()

        training_time = (datetime.now() - start_time).total_seconds()
        return ModelResult(
            model_name=model_name, model_type=model_type,
            training_score=train_score, validation_score=test_score,
            test_score=test_score, predictions=predictions,
            feature_importance=None, training_time=training_time,
        )

    def _prepare_input(self, X: pd.DataFrame) -> "torch.Tensor":
        X_values = X.values
        if self.scaler is not None:
            X_values = self.scaler.transform(X_values)
        if self.architecture == "lstm":
            X_values = self._make_sequences(X_values)
        return torch.tensor(X_values, dtype=torch.float32)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        self.model.eval()
        with torch.no_grad():
            output = self.model(self._prepare_input(X))
        if self.task == "classification":
            return output.argmax(dim=1).numpy()
        return output.numpy().flatten()

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if self.task != "classification":
            raise ValueError("predict_proba is only available for classification models")
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        self.model.eval()
        with torch.no_grad():
            logits = self.model(self._prepare_input(X))
            proba = torch.softmax(logits, dim=1)
        return proba.numpy()

    def save_model(self, filepath: str):
        if self.model is None:
            raise ValueError("No model to save")
        torch.save({
            "state_dict": self.model.state_dict(),
            "architecture": self.architecture, "task": self.task,
            "hidden_size": self.hidden_size, "num_layers": self.num_layers,
            "sequence_length": self.sequence_length, "n_classes": self.n_classes,
            "scaler": self.scaler,
        }, filepath)
        self.logger.info(f"Model saved to {filepath}")

    def load_model(self, filepath: str):
        checkpoint = torch.load(filepath, weights_only=False)
        self.architecture = checkpoint["architecture"]
        self.task = checkpoint["task"]
        self.hidden_size = checkpoint["hidden_size"]
        self.num_layers = checkpoint["num_layers"]
        self.sequence_length = checkpoint["sequence_length"]
        self.n_classes = checkpoint["n_classes"]
        self.scaler = checkpoint["scaler"]

        n_features = checkpoint["state_dict"][
            next(iter(checkpoint["state_dict"]))
        ].shape[-1] if self.architecture == "mlp" else self.hidden_size
        # Network shape can't be fully inferred from the state dict alone for
        # every layer combination, so callers should train() or reuse the
        # same constructor args before loading weights into a fresh instance.
        n_outputs = self.n_classes if self.task == "classification" else 1
        self.model = self._build_network(
            self._infer_input_size(checkpoint["state_dict"]), n_outputs
        )
        self.model.load_state_dict(checkpoint["state_dict"])
        self.model.eval()
        self.logger.info(f"Model loaded from {filepath}")

    def _infer_input_size(self, state_dict) -> int:
        first_weight = next(v for k, v in state_dict.items() if k.endswith("weight"))
        return first_weight.shape[1]
