from pathlib import Path
from typing import Dict, List, Optional

from app.assets import asset_groups
from app.strategy import BaseStrategy
from app.strategies import register

ASSETS_FILE = Path(__file__).resolve().parent / "assets.json"

_WEIGHTS: Dict[str, float] = {
    "SPY": 0.25,
    "TLT": 0.25,
    "GLD": 0.25,
    "BIL": 0.25,
}


@register("permanent")
class PermanentPortfolioStrategy(BaseStrategy):
    """Permanent Portfolio (Harry Browne) 전략.

    SPY 25%, TLT 25%, GLD 25%, BIL 25% 고정 배분.
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
