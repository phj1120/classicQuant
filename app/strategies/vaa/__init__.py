from pathlib import Path
from typing import Dict, List, Optional

from app.assets import asset_groups
from app.strategy import BaseStrategy
from app.strategies import register

ASSETS_FILE = Path(__file__).resolve().parent / "assets.json"


@register("vaa")
class VAAStrategy(BaseStrategy):
    """VAA(Vigilant Asset Allocation) 전략 구현체.

    공격자산 4개(SPY, EFA, EEM, AGG) 중 하나라도 모멘텀 < 0이면
    수비자산(LQD, IEF, SHY) 중 모멘텀 1위에 100% 투자.
    모두 >= 0이면 공격자산 모멘텀 1위에 100% 투자.
    """

    def __init__(self, assets_file: Path | None = None):
        super().__init__(assets_file or ASSETS_FILE)

    def get_universe(self) -> List[str]:
        offensive = asset_groups("offensive")
        defensive = asset_groups("defensive")
        return sorted(set(offensive + defensive))

    def select_targets(
        self, scores: Dict[str, Optional[float]]
    ) -> Dict[str, float]:
        offensive_assets = asset_groups("offensive")
        defensive_assets = asset_groups("defensive")

        # 공격자산 자체가 캐너리 역할 (모두 모멘텀 >= 0이어야 공격 모드)
        all_positive = all(
            scores.get(t) is not None and scores[t] >= 0
            for t in offensive_assets
        )

        if all_positive:
            ranked = sorted(
                [t for t in offensive_assets if scores.get(t) is not None],
                key=lambda t: scores[t],
                reverse=True,
            )
            if not ranked:
                raise RuntimeError("공격자산 모멘텀 데이터가 부족합니다.")
            return {ranked[0]: 1.0}

        # 수비 모드: 수비자산 모멘텀 1위에 100%
        ranked = sorted(
            [t for t in defensive_assets if scores.get(t) is not None],
            key=lambda t: scores[t],
            reverse=True,
        )
        if not ranked:
            raise RuntimeError("수비자산 모멘텀 데이터가 부족합니다.")
        return {ranked[0]: 1.0}
