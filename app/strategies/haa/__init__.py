from typing import ClassVar, Dict

from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import CanaryMixin
from app.assets.ticker import Ticker


@register("haa")
class HAAStrategy(CanaryMixin, BaseStrategy):
    """HAA(Hybrid Asset Allocation) 전략.

    캐너리: SPY, EEM (모두 >= 0이면 공격 모드)
    공격 모드: SPY/EFA/EEM/AGG 중 모멘텀 1위에 100%
    수비 모드: LQD/IEF/SHY 중 모멘텀 1위에 100%
    """

    ASSETS: ClassVar[Dict] = {
        "offensive": [Ticker.SPY, Ticker.EFA, Ticker.EEM, Ticker.AGG],
        "defensive": [Ticker.LQD, Ticker.IEF, Ticker.SHY],
        "canary":    [Ticker.SPY, Ticker.EEM],
    }
    CANARY_GROUP: ClassVar[str] = "canary"
    OFFENSIVE_SLOTS: ClassVar[int] = 1
