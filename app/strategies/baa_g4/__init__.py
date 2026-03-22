from typing import ClassVar, Dict

from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import CanaryMixin
from app.assets.ticker import Ticker


@register("baa_g4")
class BAAG4Strategy(CanaryMixin, BaseStrategy):
    """BAA-G4(Balanced Asset Allocation, Aggressive 4) 전략.

    캐너리: SPY, EEM
    공격 모드: SPY/EFA/EEM/AGG 중 모멘텀 1위에 100%
    수비 모드: SHY/IEF/LQD 중 1위에 100%
    """

    ASSETS: ClassVar[Dict] = {
        "offensive": [Ticker.SPY, Ticker.EFA, Ticker.EEM, Ticker.AGG],
        "defensive": [Ticker.SHY, Ticker.IEF, Ticker.LQD],
        "canary":    [Ticker.SPY, Ticker.EEM],
    }
    CANARY_GROUP: ClassVar[str] = "canary"
    OFFENSIVE_SLOTS: ClassVar[int] = 1
