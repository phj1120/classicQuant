from typing import ClassVar, Dict, List, Optional

from app.assets.assets import asset_groups
from app.strategy import BaseStrategy
from app.strategies import register
from app.assets.ticker import Ticker

_CANARY = ["SPY", "EEM"]


@register("haa")
class HAAStrategy(BaseStrategy):
    """HAA(Hybrid Asset Allocation) 전략.

    캐너리: SPY, EEM (모두 >= 0이면 공격 모드)
    공격 모드: SPY/EFA/EEM/AGG 중 모멘텀 1위에 100%
    수비 모드: LQD/IEF/SHY 중 모멘텀 1위에 100%
    """

    ASSETS: ClassVar[Dict] = {
        "offensive": [Ticker.SPY, Ticker.EFA, Ticker.EEM, Ticker.AGG],
        "defensive": [Ticker.LQD, Ticker.IEF, Ticker.SHY],
    }

    def get_universe(self) -> List[str]:
        offensive = asset_groups("offensive")
        defensive = asset_groups("defensive")
        return sorted(set(offensive + defensive))

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        offensive_assets = asset_groups("offensive")
        defensive_assets = asset_groups("defensive")

        canary_ok = all(
            scores.get(t) is not None and scores[t] >= 0
            for t in _CANARY
        )

        if canary_ok:
            ranked = sorted(
                [t for t in offensive_assets if scores.get(t) is not None],
                key=lambda t: scores[t],
                reverse=True,
            )
            if not ranked:
                raise RuntimeError("HAA: 공격자산 모멘텀 데이터 부족")
            return {ranked[0]: 1.0}

        ranked = sorted(
            [t for t in defensive_assets if scores.get(t) is not None],
            key=lambda t: scores[t],
            reverse=True,
        )
        if not ranked:
            raise RuntimeError("HAA: 수비자산 모멘텀 데이터 부족")
        return {ranked[0]: 1.0}

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        return all(
            scores.get(t) is not None and scores[t] >= 0
            for t in _CANARY
        )
