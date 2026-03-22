from typing import ClassVar, Dict

from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import SmaTrendMixin
from app.assets.ticker import Ticker


@register("gtaa")
class GTAAStrategy(SmaTrendMixin, BaseStrategy):
    """GTAA-5 (Global Tactical Asset Allocation) — Meb Faber 2009.

    SPY, EFA, VNQ, IEF, DBC 5개 자산 중 10개월 SMA 위에 있는 자산에
    균등 투자합니다. SMA 아래 자산은 SHY(현금)로 대체합니다.

    시그널: 월말 종가 > 10개월 단순이동평균 → 보유
    """

    ASSETS: ClassVar[Dict] = {
        "offensive": [Ticker.SPY, Ticker.EFA, Ticker.VNQ, Ticker.IEF, Ticker.DBC],
        "defensive": [Ticker.SHY],
    }
