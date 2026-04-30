from __future__ import annotations

import numpy as np


class FeatureNormalizer:
    def __init__(self) -> None:
        self.mean: np.ndarray | None = None
        self.std: np.ndarray | None = None

    def fit(self, x: np.ndarray) -> "FeatureNormalizer":
        self.mean = x.mean(axis=0)
        self.std = x.std(axis=0)
        self.std[self.std == 0.0] = 1.0
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        if self.mean is None or self.std is None:
            raise RuntimeError("FeatureNormalizer must be fitted first")
        return (x - self.mean) / self.std
