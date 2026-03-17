from pathlib import Path
from typing import Dict, List, Optional

from app.assets import asset_groups, group_tickers
from app.sma import SMA_200D, is_above_sma
from app.strategy import BaseStrategy
from app.strategies import register

ASSETS_FILE = Path(__file__).resolve().parent / "assets.json"

# LAA 기본 포트폴리오 (risk-on)
_BASE_WEIGHTS: Dict[str, float] = {
    "QQQ": 0.25,
    "IWD": 0.25,
    "GLD": 0.25,
    "IEF": 0.25,
}


@register("laa")
class LAAStrategy(BaseStrategy):
    """LAA (Lethargic Asset Allocation) — Wouter Keller 2019.

    기본 포트폴리오: QQQ 25%, IWD(가치주) 25%, GLD 25%, IEF 25%
    리스크-오프 조건 (두 조건 모두 충족 시 QQQ → SHY 교체):
      1. 실업률 > 12개월 이동평균 (FRED UNRATE)
      2. SPY < 200일 단순이동평균

    매우 낮은 거래 빈도 (~3년에 1회 전환)로 세금 효율적입니다.
    """

    def __init__(self, assets_file: Path | None = None):
        super().__init__(assets_file or ASSETS_FILE)

    def get_universe(self) -> List[str]:
        return sorted(
            set(
                asset_groups("risk_on")
                + asset_groups("risk_off")
                + asset_groups("trend")
            )
        )

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        risk_off = self._is_risk_off(histories)

        if risk_off:
            # QQQ → SHY 교체
            result = dict(_BASE_WEIGHTS)
            qqq_weight = result.pop("QQQ", 0.25)
            result["SHY"] = result.get("SHY", 0.0) + qqq_weight
            return result

        return dict(_BASE_WEIGHTS)

    def _is_risk_off(self, histories: Dict[str, List[float]] | None) -> bool:
        """두 조건 모두 True일 때 리스크-오프."""
        trend_signal = self._spy_below_sma(histories)
        unemployment_signal = self._unemployment_rising()
        return trend_signal and unemployment_signal

    def _spy_below_sma(self, histories: Dict[str, List[float]] | None) -> bool:
        """SPY < 200일 SMA이면 True."""
        if not histories:
            return False
        trend_groups = asset_groups("trend")
        if not trend_groups:
            return False
        for ticker in group_tickers(trend_groups[0]):
            if ticker in histories and histories[ticker]:
                result = is_above_sma(histories[ticker], SMA_200D)
                # is_above_sma=True면 SMA 위 → 정상, False면 SMA 아래 → 위험
                return result is False
        return False

    def _unemployment_rising(self) -> bool:
        """실업률 > 12개월 MA이면 True. FRED API 조회 실패 시 False."""
        try:
            from app.fred_api import get_unemployment_signal
            result = get_unemployment_signal(lookback_months=12)
            return result is True
        except Exception as e:
            print(f"  ⚠️  LAA: FRED 실업률 조회 실패 ({e}), risk-on 유지")
            return False

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        """QQQ 비중이 있으면 offensive."""
        targets = self.select_targets(scores)
        return "QQQ" in targets
