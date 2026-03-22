from typing import ClassVar, Dict

from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import CanaryMixin
from app.assets.ticker import Ticker


@register("baa_g12")
class BAAG12Strategy(CanaryMixin, BaseStrategy):
    """BAA-G12(Balanced Asset Allocation, Aggressive 12) 전략.

    캐너리: SPY, EEM (모두 >= 0이면 공격 모드)
    공격 모드: 12개 자산 중 모멘텀 1위에 100%
    수비 모드: 수비자산 (SHY/IEF/LQD) 중 1위에 100%
    """

    ASSETS: ClassVar[Dict] = {
        "offensive": [
            Ticker.SPY, Ticker.IWM, Ticker.QQQ, Ticker.VGK, Ticker.EWJ,
            Ticker.EEM, Ticker.VNQ, Ticker.DBC, Ticker.GLD, Ticker.TLT,
            Ticker.HYG, Ticker.LQD,
        ],
        "defensive": [Ticker.SHY, Ticker.IEF, Ticker.LQD],
        "canary":    [Ticker.SPY, Ticker.EEM],
    }
    CANARY_GROUP: ClassVar[str] = "canary"
    OFFENSIVE_SLOTS: ClassVar[int] = 1
