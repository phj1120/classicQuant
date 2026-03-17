from pathlib import Path
from typing import Dict, List, Optional

from app.assets import asset_groups
from app.strategy import BaseStrategy
from app.strategies import register

ASSETS_FILE = Path(__file__).resolve().parent / "assets.json"

_WEIGHTS: Dict[str, float] = {
    "SPY": 0.20,
    "VBR": 0.20,
    "TLT": 0.20,
    "SHY": 0.20,
    "GLD": 0.20,
}


@register("golden_butterfly")
class GoldenButterflyStrategy(BaseStrategy):
    """Golden Butterfly Portfolio (Tyler).

    SPY 20%, VBR(소형가치) 20%, TLT 20%, SHY 20%, GLD 20% 고정 배분.
    Permanent Portfolio의 변형으로 성장 국면에 우호적인 소형가치주를 추가.
    항상 active (정적 전략).
    """

    def __init__(self, assets_file: Path | None = None):
        super().__init__(assets_file or ASSETS_FILE)

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
