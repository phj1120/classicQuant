from typing import ClassVar, Dict

from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import FixedWeightMixin
from app.assets.ticker import Ticker


@register("all_weather")
class AllWeatherStrategy(FixedWeightMixin, BaseStrategy):
    """All Weather Portfolio (Ray Dalio) 전략.

    SPY 30%, TLT 40%, IEF 15%, GLD 7.5%, DBC 7.5% 고정 배분.
    항상 active (정적 전략).
    """

    ASSETS: ClassVar[Dict] = {
        "fixed": [Ticker.SPY, Ticker.TLT, Ticker.IEF, Ticker.GLD, Ticker.DBC],
    }
    WEIGHTS: ClassVar[Dict[str, float]] = {
        "SPY": 0.30,
        "TLT": 0.40,
        "IEF": 0.15,
        "GLD": 0.075,
        "DBC": 0.075,
    }
