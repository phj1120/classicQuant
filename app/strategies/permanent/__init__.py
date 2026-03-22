from typing import ClassVar, Dict

from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import FixedWeightMixin
from app.assets.ticker import Ticker


@register("permanent")
class PermanentPortfolioStrategy(FixedWeightMixin, BaseStrategy):
    """Permanent Portfolio (Harry Browne) 전략.

    SPY 25%, TLT 25%, GLD 25%, BIL 25% 고정 배분.
    항상 active (정적 전략).
    """

    ASSETS: ClassVar[Dict] = {
        "fixed": [Ticker.SPY, Ticker.TLT, Ticker.GLD, Ticker.BIL],
    }
    WEIGHTS: ClassVar[Dict[str, float]] = {
        "SPY": 0.25,
        "TLT": 0.25,
        "GLD": 0.25,
        "BIL": 0.25,
    }
