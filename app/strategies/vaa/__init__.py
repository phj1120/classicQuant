from typing import ClassVar, Dict

from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import CanaryMixin
from app.assets.ticker import Ticker


@register("vaa")
class VAAStrategy(CanaryMixin, BaseStrategy):
    """VAA(Vigilant Asset Allocation) 전략 구현체.

    공격자산 4개(SPY, EFA, EEM, AGG) 중 하나라도 모멘텀 < 0이면
    수비자산(LQD, IEF, SHY) 중 모멘텀 1위에 100% 투자.
    모두 >= 0이면 공격자산 모멘텀 1위에 100% 투자.
    """

    ASSETS: ClassVar[Dict] = {
        "offensive": [Ticker.SPY, Ticker.EFA, Ticker.EEM, Ticker.AGG],
        "defensive": [Ticker.LQD, Ticker.IEF, Ticker.SHY],
    }
    # CANARY_GROUP = None: offensive 자산 전체를 카나리아로 사용
    CANARY_GROUP: ClassVar[None] = None
    OFFENSIVE_SLOTS: ClassVar[int] = 1
