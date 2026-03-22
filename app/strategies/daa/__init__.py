from typing import ClassVar, Dict

from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import CanaryMixin
from app.assets.ticker import Ticker


@register("daa")
class DAAStrategy(CanaryMixin, BaseStrategy):
    """DAA(Dynamic Asset Allocation) 전략 구현체.

    캐너리 자산(VWO, BND) 모멘텀이 모두 >= 0이면 공격자산 상위 2개에 50/50,
    아니면 수비자산 1위에 100% 투자.
    """

    ASSETS: ClassVar[Dict] = {
        "offensive": [
            Ticker.SPY, Ticker.IWM, Ticker.QQQ, Ticker.VGK, Ticker.EWJ,
            Ticker.EEM, Ticker.VNQ, Ticker.DBC, Ticker.GLD, Ticker.TLT,
            Ticker.HYG, Ticker.LQD,
        ],
        "defensive": [Ticker.SHY, Ticker.IEF, Ticker.LQD],
        "canary":    [Ticker.VWO, Ticker.BND],
    }
    CANARY_GROUP: ClassVar[str] = "canary"
    OFFENSIVE_SLOTS: ClassVar[int] = 2
