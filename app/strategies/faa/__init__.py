from typing import ClassVar, Dict, List, Optional

from app.assets.assets import asset_groups
from app.indicators.factor import compute_correlation, compute_ewp_prices, compute_volatility
from app.strategy import BaseStrategy
from app.strategies import register
from app.strategies.mixins import AnnualizedReturnScoreMixin
from app.assets.ticker import Ticker

# FAA 랭킹 가중치 (Keller & van Putten 2012)
_WR = 1.0   # 모멘텀 가중치
_WV = 0.5   # 변동성 가중치
_WC = 0.5   # 상관관계 가중치
_TOP_N = 3  # 상위 N개 선택


@register("faa")
class FAAStrategy(AnnualizedReturnScoreMixin, BaseStrategy):
    """FAA (Flexible Asset Allocation) — Keller & van Putten 2012.

    7개 자산(SPY, EFA, EEM, AGG, DBC, VNQ, SHY)을
    모멘텀·변동성·상관관계 복합 랭킹으로 상위 3개 선택.
    절대 모멘텀 음수인 자산은 SHY(현금)로 대체합니다.

    복합 랭킹 = wR×R_mom + wV×R_vol + wC×R_corr (낮을수록 좋음)
    """

    ASSETS: ClassVar[Dict] = {
        "universe":  [Ticker.SPY, Ticker.EFA, Ticker.EEM, Ticker.AGG, Ticker.DBC, Ticker.VNQ, Ticker.SHY],
        "defensive": [Ticker.SHY],
    }

    def get_universe(self) -> List[str]:
        return sorted(set(asset_groups("universe") + asset_groups("defensive")))

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        universe = asset_groups("universe")
        defensive = asset_groups("defensive")
        cash = defensive[0]

        # --- 모멘텀 랭킹 ---
        valid = [g for g in universe if scores.get(g) is not None]
        if not valid:
            return {cash: 1.0}

        sorted_by_mom = sorted(valid, key=lambda g: scores[g], reverse=True)
        mom_rank = {g: i + 1 for i, g in enumerate(sorted_by_mom)}

        # --- 변동성·상관관계 랭킹 (histories 있을 때만) ---
        vol_rank: Dict[str, int] = {g: len(valid) for g in valid}
        corr_rank: Dict[str, int] = {g: len(valid) for g in valid}

        if histories:
            group_prices = self._load_group_prices(valid, histories)

            if len(group_prices) >= 2:
                ewp = compute_ewp_prices(group_prices)

                vols = {g: compute_volatility(p) for g, p in group_prices.items()}
                valid_vol = [g for g in valid if vols.get(g) is not None]
                sorted_by_vol = sorted(valid_vol, key=lambda g: vols[g])
                vol_rank.update({g: i + 1 for i, g in enumerate(sorted_by_vol)})

                if ewp:
                    corrs = {
                        g: compute_correlation(group_prices[g], ewp)
                        for g in group_prices
                    }
                    valid_corr = [g for g in valid if corrs.get(g) is not None]
                    sorted_by_corr = sorted(valid_corr, key=lambda g: corrs[g])
                    corr_rank.update({g: i + 1 for i, g in enumerate(sorted_by_corr)})

        # --- 복합 랭킹 ---
        combined = {
            g: _WR * mom_rank[g] + _WV * vol_rank[g] + _WC * corr_rank[g]
            for g in valid
        }
        top = sorted(valid, key=lambda g: combined[g])[:_TOP_N]

        # --- 절대 모멘텀 음수 → SHY 대체 ---
        result: Dict[str, float] = {}
        n = len(top)
        if n == 0:
            return {cash: 1.0}
        weight = 1.0 / n
        for g in top:
            if scores[g] is not None and scores[g] > 0:
                result[g] = result.get(g, 0.0) + weight
            else:
                result[cash] = result.get(cash, 0.0) + weight

        return result

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        universe = asset_groups("universe")
        risky = [g for g in universe if g != "SHY"]
        return any(scores.get(g) is not None and scores[g] > 0 for g in risky)
