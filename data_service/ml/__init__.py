"""
Machine Learning Module for Trading System
Provides ML models for prediction and classification, plus feature engineering,
evaluation, ensembling, hyperparameter optimization, and deep learning.
"""

try:
    from .ml_models import MLModelManager, PredictionModel, ClassificationModel
    from .feature_engineering import FeatureEngineer
    from .model_evaluation import ModelEvaluator
    from .ensemble_models import EnsembleModel
    from .optimization import MLOptimizer
except ImportError as e:
    MLModelManager = None
    PredictionModel = None
    ClassificationModel = None
    FeatureEngineer = None
    ModelEvaluator = None
    EnsembleModel = None
    MLOptimizer = None

# DeepLearningModel requires torch, which is heavier than the rest of the
# base ml deps -- guard it separately so the rest of the package still works
# without the `ai` extra installed.
try:
    from .deep_learning import DeepLearningModel
except ImportError:
    DeepLearningModel = None

__all__ = [
    'MLModelManager',
    'PredictionModel',
    'ClassificationModel',
    'FeatureEngineer',
    'ModelEvaluator',
    'EnsembleModel',
    'MLOptimizer',
    'DeepLearningModel'
]
