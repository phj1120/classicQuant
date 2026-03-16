from pathlib import Path
from typing import Dict, List, Optional

from app.assets import asset_groups
from app.strategy import BaseStrategy
from app.strategies import register

ASSETS_FILE = Path(__file__).resolve().parent / "assets.json"


@register("gem")
class GEMStrategy(BaseStrategy):
    """GEM(Global Equity Momentum) 전략.

    SPY vs EFA 상대 모멘텀 비교 → 승자 선택
    승자의 절대 모멘텀(score) > 0 → 승자에 투자
    승자의 절대 모멘텀 <= 0 → AGG(채권)에 투자
    is_active: SPY 또는 EFA의 모멘텀 >= 0
    """

    def __init__(self, assets_file: Path | None = None):
        super().__init__(assets_file or ASSETS_FILE)

    def get_universe(self) -> List[str]:
        offensive = asset_groups("offensive")
        defensive = asset_groups("defensive")
        return sorted(set(offensive + defensive))

    def score_from_returns(self, returns: Dict[str, Optional[float]]) -> Optional[float]:
        """Antonacci 원논문: 12개월 수익률만 사용 (복합 공식 X)."""
        return returns.get("r12m")

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        offensive_assets = asset_groups("offensive")   # SPY, EFA
        defensive_assets = asset_groups("defensive")   # AGG

        # 상대 모멘텀: 공격자산 중 점수 최고 선택
        ranked_off = sorted(
            [t for t in offensive_assets if scores.get(t) is not None],
            key=lambda t: scores[t],
            reverse=True,
        )
        if not ranked_off:
            raise RuntimeError("GEM: 공격자산 모멘텀 데이터 부족")

        winner = ranked_off[0]
        winner_score = scores[winner]

        # 절대 모멘텀: 승자의 score > 0이면 승자에 투자
        if winner_score is not None and winner_score > 0:
            return {winner: 1.0}

        # 절대 모멘텀 음수 → 채권으로
        ranked_def = sorted(
            [t for t in defensive_assets if scores.get(t) is not None],
            key=lambda t: scores[t],
            reverse=True,
        )
        if not ranked_def:
            raise RuntimeError("GEM: 수비자산 모멘텀 데이터 부족")
        return {ranked_def[0]: 1.0}

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        offensive_assets = asset_groups("offensive")
        return any(
            scores.get(t) is not None and scores[t] >= 0
            for t in offensive_assets
        )
