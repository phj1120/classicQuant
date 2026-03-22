from typing import ClassVar, Dict

from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import SmaTrendMixin
from app.assets.ticker import Ticker


@register("ivy")
class IvyStrategy(SmaTrendMixin, BaseStrategy):
    """Ivy Portfolio (Faber & Richardson 2009).

    VTI, EFA, VNQ, IEF, DBC 5개 자산 중 10개월 SMA 위에 있는 자산에
    균등 투자합니다. SMA 아래 자산은 SHY(현금)로 대체합니다.

    GTAA-5와 동일한 SMA 로직을 사용하며, Ivy League 기금 배분을
    ETF로 모방한 포트폴리오입니다.
    """

    ASSETS: ClassVar[Dict] = {
        "offensive": [Ticker.VTI, Ticker.EFA, Ticker.VNQ, Ticker.IEF, Ticker.DBC],
        "defensive": [Ticker.SHY],
    }
