from typing import ClassVar, Dict, List, Optional

from app.assets import asset_groups
from app.strategy import BaseStrategy
from app.strategies import register
from app.ticker import Ticker

_WEIGHTS: Dict[str, float] = {
    "SPY": 0.30,
    "TLT": 0.40,
    "IEF": 0.15,
    "GLD": 0.075,
    "DBC": 0.075,
}


@register("all_weather")
class AllWeatherStrategy(BaseStrategy):
    """All Weather Portfolio (Ray Dalio) 전략.

    SPY 30%, TLT 40%, IEF 15%, GLD 7.5%, DBC 7.5% 고정 배분.
    항상 active (정적 전략).
    """

    ASSETS: ClassVar[Dict] = {
        "fixed": [Ticker.SPY, Ticker.TLT, Ticker.IEF, Ticker.GLD, Ticker.DBC],
    }

    def get_universe(self) -> List[str]:
        return sorted(asset_groups("fixed"))

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        return dict(_WEIGHTS)

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        return True
