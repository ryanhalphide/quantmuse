import unittest

import numpy as np
import pandas as pd
import pytest

from data_service.ml import (
    PredictionModel, ClassificationModel, ModelEvaluator, EnsembleModel, MLOptimizer
)
from data_service.ml.ml_models import ModelConfig


def make_regression_data(n=200, n_features=4, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, n_features)),
                     columns=[f"f{i}" for i in range(n_features)])
    y = pd.Series(X.sum(axis=1) + rng.normal(scale=0.1, size=n), name="target")
    return X, y


def make_classification_data(n=200, n_features=4, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, n_features)),
                     columns=[f"f{i}" for i in range(n_features)])
    y = pd.Series((X["f0"] + X["f1"] > 0).astype(int), name="target")
    return X, y


class _PicklableDummyModel:
    def predict(self, X):
        return np.full(len(X), 42.0)


class TestModelEvaluator(unittest.TestCase):
    def test_evaluate_regression(self):
        X, y = make_regression_data()
        model = PredictionModel(model_type="linear_regression")
        model.train(X, y, ModelConfig(
            model_type="linear_regression", parameters={}, feature_columns=list(X.columns),
            target_column="target", cross_validate=False,
        ))
        report = ModelEvaluator().evaluate(model, X, y, model_type="regression")
        self.assertIn("r2", report.metrics)
        self.assertIn("rmse", report.metrics)
        self.assertIsNotNone(report.residuals)
        self.assertGreater(report.metrics["r2"], 0.5)

    def test_evaluate_classification(self):
        X, y = make_classification_data()
        model = ClassificationModel(model_type="logistic_regression")
        model.train(X, y, ModelConfig(
            model_type="logistic_regression", parameters={}, feature_columns=list(X.columns),
            target_column="target", cross_validate=False,
        ))
        report = ModelEvaluator().evaluate(model, X, y, model_type="classification")
        self.assertIn("accuracy", report.metrics)
        self.assertIsNotNone(report.confusion)
        self.assertIn("roc_auc", report.metrics)  # binary + predict_proba -> ROC computed

    def test_evaluate_invalid_type(self):
        X, y = make_regression_data()
        model = PredictionModel()
        model.train(X, y)
        with self.assertRaises(ValueError):
            ModelEvaluator().evaluate(model, X, y, model_type="nonsense")

    def test_permutation_importance(self):
        X, y = make_regression_data()
        model = PredictionModel(model_type="linear_regression")
        model.train(X, y, ModelConfig(
            model_type="linear_regression", parameters={}, feature_columns=list(X.columns),
            target_column="target", cross_validate=False, scale_features=False,
        ))
        importances = ModelEvaluator().permutation_importance(model, X, y, n_repeats=3)
        self.assertEqual(set(importances.keys()), set(X.columns))


class TestEnsembleModel(unittest.TestCase):
    def test_regression_weighted_average(self):
        class ConstantModel:
            def __init__(self, value):
                self.value = value
            def predict(self, X):
                return np.full(len(X), self.value)

        ensemble = EnsembleModel(model_type="regression")
        ensemble.add_model("a", ConstantModel(10), weight=1)
        ensemble.add_model("b", ConstantModel(20), weight=1)
        preds = ensemble.predict(pd.DataFrame({"x": [1, 2, 3]}))
        np.testing.assert_allclose(preds, [15, 15, 15])

    def test_regression_weighted_average_unequal_weights(self):
        class ConstantModel:
            def __init__(self, value):
                self.value = value
            def predict(self, X):
                return np.full(len(X), self.value)

        ensemble = EnsembleModel(model_type="regression")
        ensemble.add_model("a", ConstantModel(0), weight=3)
        ensemble.add_model("b", ConstantModel(100), weight=1)
        preds = ensemble.predict(pd.DataFrame({"x": [1]}))
        self.assertAlmostEqual(preds[0], 25.0)

    def test_classification_majority_vote(self):
        class FixedModel:
            def __init__(self, labels):
                self.labels = labels
            def predict(self, X):
                return np.array(self.labels)

        ensemble = EnsembleModel(model_type="classification")
        ensemble.add_model("a", FixedModel([1, 0, 1]))
        ensemble.add_model("b", FixedModel([1, 0, 0]))
        ensemble.add_model("c", FixedModel([0, 0, 1]))
        preds = ensemble.predict(pd.DataFrame({"x": [1, 2, 3]}))
        np.testing.assert_array_equal(preds, [1, 0, 1])

    def test_remove_model(self):
        class DummyModel:
            def predict(self, X):
                return np.zeros(len(X))
        ensemble = EnsembleModel()
        ensemble.add_model("a", DummyModel())
        ensemble.remove_model("a")
        with self.assertRaises(ValueError):
            ensemble.predict(pd.DataFrame({"x": [1]}))

    def test_invalid_model_type(self):
        with self.assertRaises(ValueError):
            EnsembleModel(model_type="not-a-type")

    def test_save_load_roundtrip(self):
        import tempfile, os
        ensemble = EnsembleModel(model_type="regression")
        ensemble.add_model("a", _PicklableDummyModel())
        f = tempfile.NamedTemporaryFile(suffix=".joblib", delete=False)
        f.close()
        try:
            ensemble.save_model(f.name)
            loaded = EnsembleModel()
            loaded.load_model(f.name)
            preds = loaded.predict(pd.DataFrame({"x": [1, 2]}))
            np.testing.assert_allclose(preds, [42.0, 42.0])
        finally:
            os.unlink(f.name)


class TestMLOptimizer(unittest.TestCase):
    def test_grid_search_on_raw_estimator(self):
        from sklearn.linear_model import Ridge
        X, y = make_regression_data(n=60)
        opt = MLOptimizer()
        result = opt.grid_search(Ridge(), {"alpha": [0.1, 1.0, 10.0]}, X, y, cv=3)
        self.assertIn("alpha", result.best_params)
        self.assertGreater(result.best_score, -1.0)

    def test_grid_search_on_wrapped_model(self):
        X, y = make_regression_data(n=60)
        model = PredictionModel(model_type="ridge")
        opt = MLOptimizer()
        result = opt.grid_search(model, {"alpha": [0.1, 1.0]}, X, y, cv=3)
        self.assertIn("alpha", result.best_params)

    def test_random_search(self):
        from sklearn.ensemble import RandomForestRegressor
        X, y = make_regression_data(n=60)
        opt = MLOptimizer()
        result = opt.random_search(
            RandomForestRegressor(random_state=0),
            {"n_estimators": [10, 20, 30], "max_depth": [2, 4, None]},
            X, y, n_iter=3, cv=3,
        )
        self.assertIn("n_estimators", result.best_params)
        self.assertGreater(result.search_time, 0)


class TestDeepLearningModel(unittest.TestCase):
    def setUp(self):
        pytest.importorskip("torch")

    def test_mlp_regression_train_predict(self):
        from data_service.ml import DeepLearningModel
        X, y = make_regression_data(n=150)
        model = DeepLearningModel(architecture="mlp", task="regression",
                                  hidden_size=16, epochs=5)
        result = model.train(X, y)
        self.assertEqual(result.model_type, "regression")
        preds = model.predict(X)
        self.assertEqual(len(preds), len(X))

    def test_mlp_classification_train_predict_proba(self):
        from data_service.ml import DeepLearningModel
        X, y = make_classification_data(n=150)
        model = DeepLearningModel(architecture="mlp", task="classification",
                                  hidden_size=16, epochs=5)
        result = model.train(X, y)
        self.assertEqual(result.model_type, "classification")
        proba = model.predict_proba(X)
        self.assertEqual(proba.shape[0], len(X))
        np.testing.assert_allclose(proba.sum(axis=1), np.ones(len(X)), atol=1e-4)

    def test_lstm_regression_train_predict(self):
        from data_service.ml import DeepLearningModel
        X, y = make_regression_data(n=150)
        model = DeepLearningModel(architecture="lstm", task="regression",
                                  hidden_size=8, sequence_length=5, epochs=3)
        result = model.train(X, y)
        self.assertEqual(result.model_type, "regression")
        preds = model.predict(X)
        # LSTM predictions are shorter than input by sequence_length.
        self.assertEqual(len(preds), len(X) - model.sequence_length)

    def test_predict_without_train_raises(self):
        from data_service.ml import DeepLearningModel
        model = DeepLearningModel(architecture="mlp", task="regression")
        with self.assertRaises(ValueError):
            model.predict(pd.DataFrame({"x": [1, 2]}))

    def test_invalid_architecture(self):
        from data_service.ml import DeepLearningModel
        with self.assertRaises(ValueError):
            DeepLearningModel(architecture="rnn")


if __name__ == "__main__":
    unittest.main()
