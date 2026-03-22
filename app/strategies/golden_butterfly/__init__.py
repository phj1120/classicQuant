from typing import ClassVar, Dict

from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import FixedWeightMixin
from app.assets.ticker import Ticker


@register("golden_butterfly")
class GoldenButterflyStrategy(FixedWeightMixin, BaseStrategy):
    """Golden Butterfly Portfolio (Tyler).

    SPY 20%, VBR(소형가치) 20%, TLT 20%, SHY 20%, GLD 20% 고정 배분.
    Permanent Portfolio의 변형으로 성장 국면에 우호적인 소형가치주를 추가.
    항상 active (정적 전략).
    """

    ASSETS: ClassVar[Dict] = {
        "fixed": [Ticker.SPY, Ticker.VBR, Ticker.TLT, Ticker.SHY, Ticker.GLD],
    }
    WEIGHTS: ClassVar[Dict[str, float]] = {
        "SPY": 0.20,
        "VBR": 0.20,
        "TLT": 0.20,
        "SHY": 0.20,
        "GLD": 0.20,
    }
