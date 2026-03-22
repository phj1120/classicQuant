from typing import ClassVar, Dict, List, Optional

from app.assets import asset_groups, group_tickers
from app.sma import SMA_10M, is_above_sma
from app.strategy import BaseStrategy
from app.strategies import register
from app.ticker import Ticker


@register("ivy")
class IvyStrategy(BaseStrategy):
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

    def get_universe(self) -> List[str]:
        return sorted(set(asset_groups("offensive") + asset_groups("defensive")))

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        offensive = asset_groups("offensive")
        defensive = asset_groups("defensive")

        if histories:
            above = []
            for group in offensive:
                prices = None
                for ticker in group_tickers(group):
                    if ticker in histories and histories[ticker]:
                        prices = histories[ticker]
                        break
                if prices and is_above_sma(prices, SMA_10M) is True:
                    above.append(group)
        else:
            above = [g for g in offensive if scores.get(g) is not None and scores[g] > 0]

        if not above:
            return {defensive[0]: 1.0}

        weight = 1.0 / len(above)
        return {g: weight for g in above}

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        offensive = asset_groups("offensive")
        return any(scores.get(g) is not None and scores[g] > 0 for g in offensive)
