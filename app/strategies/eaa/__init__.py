import math
from pathlib import Path
from typing import Dict, List, Optional

from app.assets import asset_groups, group_tickers
from app.factor import compute_correlation, compute_ewp_prices, compute_volatility
from app.strategy import BaseStrategy
from app.strategies import register

ASSETS_FILE = Path(__file__).resolve().parent / "assets.json"

# EAA 탄성 지수 (Keller & Butler 2014 기본값)
_WR = 1.0   # 모멘텀 탄성
_WV = 1.0   # 변동성 탄성
_WC = 0.5   # 상관관계 탄성
_TOP_N = 3  # 상위 N개 선택


@register("eaa")
class EAAStrategy(BaseStrategy):
    """EAA (Elastic Asset Allocation) — Keller & Butler 2014.

    7개 글로벌 자산을 탄성 점수로 랭킹하여 상위 3개에 비례 투자.
    탄성 점수: zi = (ri^wR × (1-ci)^wC / vi^wV)
    절대 모멘텀 음수인 자산은 SHY(현금)로 대체합니다.
    """

    def __init__(self, assets_file: Path | None = None):
        super().__init__(assets_file or ASSETS_FILE)

    def get_universe(self) -> List[str]:
        return sorted(set(asset_groups("universe") + asset_groups("defensive")))

    def score_from_returns(self, returns: Dict[str, Optional[float]]) -> Optional[float]:
        """EAA: 연율화 수익률 평균."""
        r1 = returns.get("r1m")
        r3 = returns.get("r3m")
        r6 = returns.get("r6m")
        r12 = returns.get("r12m")
        values = [v for v in (r1 * 12 if r1 is not None else None,
                               r3 * 4 if r3 is not None else None,
                               r6 * 2 if r6 is not None else None,
                               r12) if v is not None]
        if not values:
            return None
        return sum(values) / len(values)

    def _elastic_score(
        self,
        momentum: float,
        volatility: Optional[float],
        correlation: Optional[float],
    ) -> float:
        """탄성 점수 계산. 데이터 없으면 모멘텀만 사용."""
        if momentum <= 0:
            return 0.0
        try:
            ri = max(momentum, 1e-10) ** _WR
            vi = (volatility if volatility and volatility > 1e-10 else 0.2) ** _WV
            ci = max(0.0, 1.0 - (correlation if correlation is not None else 0.0)) ** _WC
            return (ri * ci) / vi
        except (ValueError, ZeroDivisionError):
            return 0.0

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        universe = asset_groups("universe")
        defensive = asset_groups("defensive")
        cash = defensive[0]

        valid = [g for g in universe if scores.get(g) is not None]
        if not valid:
            return {cash: 1.0}

        # 변동성·상관관계 계산 (histories 있을 때)
        vols: Dict[str, Optional[float]] = {g: None for g in valid}
        corrs: Dict[str, Optional[float]] = {g: None for g in valid}

        if histories:
            group_prices: Dict[str, List[float]] = {}
            for group in valid:
                for ticker in group_tickers(group):
                    if ticker in histories and len(histories[ticker]) > 20:
                        group_prices[group] = histories[ticker]
                        break

            if len(group_prices) >= 2:
                for g, p in group_prices.items():
                    vols[g] = compute_volatility(p)

                ewp = compute_ewp_prices(group_prices)
                if ewp:
                    for g, p in group_prices.items():
                        corrs[g] = compute_correlation(p, ewp)

        # 탄성 점수 계산
        elastic: Dict[str, float] = {
            g: self._elastic_score(scores[g], vols[g], corrs[g])
            for g in valid
        }

        # 상위 TOP_N 선택 (탄성 점수 > 0인 것만)
        ranked = sorted(
            [g for g in valid if elastic[g] > 0],
            key=lambda g: elastic[g],
            reverse=True,
        )[:_TOP_N]

        if not ranked:
            return {cash: 1.0}

        # 탄성 점수 비례 가중치
        total_score = sum(elastic[g] for g in ranked)
        result: Dict[str, float] = {}
        for g in ranked:
            w = elastic[g] / total_score if total_score > 0 else 1.0 / len(ranked)
            # 절대 모멘텀 음수 → SHY 대체
            if scores[g] is not None and scores[g] > 0:
                result[g] = result.get(g, 0.0) + w
            else:
                result[cash] = result.get(cash, 0.0) + w

        return result if result else {cash: 1.0}

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        universe = asset_groups("universe")
        return any(scores.get(g) is not None and scores[g] > 0 for g in universe)
