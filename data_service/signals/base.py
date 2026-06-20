"""Signal provider interfaces and composite scoring.

A "signal" here is an informational, directional read on an asset derived from
real market data (technical indicators, news sentiment). It is NOT a profit
guarantee -- it is one input among many. Providers fetch raw signal components;
the composite scorer blends them into a single score in [-1, 1] with a label.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# Composite score thresholds -> label.
def score_to_label(score: float) -> str:
    if score >= 0.35:
        return "BULLISH"
    if score >= 0.15:
        return "SOMEWHAT_BULLISH"
    if score > -0.15:
        return "NEUTRAL"
    if score > -0.35:
        return "SOMEWHAT_BEARISH"
    return "BEARISH"


@dataclass
class SignalResult:
    """A composite signal for one asset."""

    symbol: str
    score: float  # in [-1, 1]; positive = bullish
    label: str
    components: Dict[str, Optional[float]] = field(default_factory=dict)
    rationale: List[str] = field(default_factory=list)
    provider: str = ""
    as_of: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


class SignalProvider:
    """Abstract base for a signal provider.

    Subclasses implement the component fetchers; ``composite_signal`` blends
    whatever components are available into a single SignalResult. Components
    that fail to fetch are skipped (None) rather than failing the whole signal.
    """

    name: str = "base"

    # Weights for blending available components into the composite score.
    weights: Dict[str, float] = {"rsi": 0.35, "macd": 0.30, "sentiment": 0.35}

    def rsi_score(self, symbol: str) -> Optional[float]:
        """Return an RSI-derived score in [-1, 1], or None if unavailable."""
        raise NotImplementedError

    def macd_score(self, symbol: str) -> Optional[float]:
        """Return a MACD-derived score in [-1, 1], or None if unavailable."""
        raise NotImplementedError

    def sentiment_score(self, symbol: str) -> Optional[float]:
        """Return a news-sentiment score in [-1, 1], or None if unavailable."""
        raise NotImplementedError

    def composite_signal(self, symbol: str) -> SignalResult:
        components: Dict[str, Optional[float]] = {
            "rsi": self._safe(self.rsi_score, symbol),
            "macd": self._safe(self.macd_score, symbol),
            "sentiment": self._safe(self.sentiment_score, symbol),
        }
        rationale: List[str] = []
        weighted_sum = 0.0
        weight_total = 0.0
        for key, value in components.items():
            if value is None:
                rationale.append(f"{key}: unavailable")
                continue
            w = self.weights.get(key, 0.0)
            weighted_sum += w * value
            weight_total += w
            rationale.append(f"{key}: {round(value, 3)} (weight {w})")

        score = round(weighted_sum / weight_total, 4) if weight_total > 0 else 0.0
        return SignalResult(
            symbol=symbol,
            score=score,
            label=score_to_label(score),
            components=components,
            rationale=rationale,
            provider=self.name,
        )

    @staticmethod
    def _safe(fn, symbol: str) -> Optional[float]:
        """Run a component fetcher, swallowing errors into None."""
        try:
            return fn(symbol)
        except Exception:
            return None


def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))
