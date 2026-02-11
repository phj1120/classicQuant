from pathlib import Path
from typing import Dict, List, Optional

from app.assets import asset_groups
from app.strategy import BaseStrategy
from app.strategies import register

ASSETS_FILE = Path(__file__).resolve().parent / "assets.json"


@register("daa")
class DAAStrategy(BaseStrategy):
    """DAA(Dynamic Asset Allocation) 전략 구현체.

    캐너리 자산(VWO, BND) 모멘텀이 모두 >= 0이면 공격자산 상위 2개에 50/50,
    아니면 수비자산 1위에 100% 투자.
    """

    def __init__(self, assets_file: Path | None = None):
        super().__init__(assets_file or ASSETS_FILE)

    def get_universe(self) -> List[str]:
        offensive = asset_groups("offensive")
        defensive = asset_groups("defensive")
        canary = asset_groups("canary")
        return sorted(set(offensive + defensive + canary))

    def select_targets(
        self, scores: Dict[str, Optional[float]]
    ) -> Dict[str, float]:
        canary_assets = asset_groups("canary")
        defensive_assets = asset_groups("defensive")
        offensive_assets = asset_groups("offensive")

        canary_scores = [scores.get(t) for t in canary_assets]
        canary_ok = all(s is not None and s >= 0 for s in canary_scores)

        if canary_ok:
            ranked = sorted(
                [t for t in offensive_assets if scores.get(t) is not None],
                key=lambda t: scores[t],
                reverse=True,
            )
            if len(ranked) < 2:
                raise RuntimeError("공격자산 모멘텀 데이터가 부족합니다.")
            top = ranked[:2]
            return {top[0]: 0.5, top[1]: 0.5}

        ranked = sorted(
            [t for t in defensive_assets if scores.get(t) is not None],
            key=lambda t: scores[t],
            reverse=True,
        )
        if not ranked:
            raise RuntimeError("수비자산 모멘텀 데이터가 부족합니다.")
        return {ranked[0]: 1.0}
