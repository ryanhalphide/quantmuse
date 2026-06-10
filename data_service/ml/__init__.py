"""
Machine Learning Module for Trading System
Provides ML models for prediction and classification, plus feature engineering
"""

try:
    from .ml_models import MLModelManager, PredictionModel, ClassificationModel
    from .feature_engineering import FeatureEngineer
except ImportError as e:
    MLModelManager = None
    PredictionModel = None
    ClassificationModel = None
    FeatureEngineer = None

__all__ = [
    'MLModelManager',
    'PredictionModel',
    'ClassificationModel',
    'FeatureEngineer'
]
