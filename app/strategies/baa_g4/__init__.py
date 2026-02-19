from pathlib import Path
from typing import Dict, List, Optional

from app.assets import asset_groups
from app.strategy import BaseStrategy
from app.strategies import register

ASSETS_FILE = Path(__file__).resolve().parent / "assets.json"

_CANARY = ["SPY", "EEM"]


@register("baa_g4")
class BAAG4Strategy(BaseStrategy):
    """BAA-G4(Balanced Asset Allocation, Aggressive 4) 전략.

    캐너리: SPY, EEM
    공격 모드: SPY/EFA/EEM/AGG 중 모멘텀 1위에 100%
    수비 모드: SHY/IEF/LQD 중 1위에 100%
    """

    def __init__(self, assets_file: Path | None = None):
        super().__init__(assets_file or ASSETS_FILE)

    def get_universe(self) -> List[str]:
        offensive = asset_groups("offensive")
        defensive = asset_groups("defensive")
        return sorted(set(offensive + defensive))

    def select_targets(self, scores: Dict[str, Optional[float]]) -> Dict[str, float]:
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
                raise RuntimeError("BAA-G4: 공격자산 모멘텀 데이터 부족")
            return {ranked[0]: 1.0}

        ranked = sorted(
            [t for t in defensive_assets if scores.get(t) is not None],
            key=lambda t: scores[t],
            reverse=True,
        )
        if not ranked:
            raise RuntimeError("BAA-G4: 수비자산 모멘텀 데이터 부족")
        return {ranked[0]: 1.0}

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        return all(
            scores.get(t) is not None and scores[t] >= 0
            for t in _CANARY
        )
