from pathlib import Path
from typing import Dict, List, Optional

from app.assets import asset_groups
from app.strategy import BaseStrategy
from app.strategies import register

ASSETS_FILE = Path(__file__).resolve().parent / "assets.json"


@register("paa")
class PAAStrategy(BaseStrategy):
    """PAA(Protective Asset Allocation) 전략 구현체.

    공격자산 12개 중 모멘텀 >= 0인 자산 수(n)에 따라 보호 비율 결정.
    보호 비율 = (12 - n) / 12 → 수비자산 1위에 투자
    나머지 = 공격자산 1위에 투자
    is_active: n >= 6 (절반 이상이 양수)
    """

    N_OFFENSIVE = 12

    def __init__(self, assets_file: Path | None = None):
        super().__init__(assets_file or ASSETS_FILE)

    def get_universe(self) -> List[str]:
        offensive = asset_groups("offensive")
        defensive = asset_groups("defensive")
        return sorted(set(offensive + defensive))

    def select_targets(self, scores: Dict[str, Optional[float]]) -> Dict[str, float]:
        offensive_assets = asset_groups("offensive")
        defensive_assets = asset_groups("defensive")

        # 모멘텀 양수인 공격자산 개수
        positive_count = sum(
            1 for t in offensive_assets
            if scores.get(t) is not None and scores[t] >= 0
        )
        n = len(offensive_assets)
        protection_ratio = (n - positive_count) / n
        offensive_ratio = 1.0 - protection_ratio

        result: Dict[str, float] = {}

        # 수비 비율: 수비자산 1위에
        if protection_ratio > 1e-9:
            ranked_def = sorted(
                [t for t in defensive_assets if scores.get(t) is not None],
                key=lambda t: scores[t],
                reverse=True,
            )
            if ranked_def:
                result[ranked_def[0]] = protection_ratio

        # 공격 비율: 공격자산 1위에
        if offensive_ratio > 1e-9:
            ranked_off = sorted(
                [t for t in offensive_assets if scores.get(t) is not None],
                key=lambda t: scores[t],
                reverse=True,
            )
            if ranked_off:
                top = ranked_off[0]
                result[top] = result.get(top, 0.0) + offensive_ratio

        if not result:
            raise RuntimeError("PAA: 모멘텀 데이터가 부족합니다.")

        return result

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        """n >= 6이면 오펜시브 모드."""
        offensive_assets = asset_groups("offensive")
        positive_count = sum(
            1 for t in offensive_assets
            if scores.get(t) is not None and scores[t] >= 0
        )
        return positive_count >= (len(offensive_assets) // 2)
