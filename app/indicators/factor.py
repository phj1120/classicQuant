"""변동성·상관관계 계산 유틸리티.

FAA, EAA 전략의 복합 랭킹 점수 계산에 사용됩니다.
"""
import math
from typing import Dict, List, Optional

from app.constants import LOOKBACK_DAYS

_LOOKBACK = LOOKBACK_DAYS["12m"]  # 252일


def _daily_returns(prices: List[float], lookback: int = _LOOKBACK) -> List[float]:
    """lookback 기간의 일별 수익률 시계열 반환."""
    if len(prices) < lookback + 1:
        n = len(prices)
    else:
        n = lookback + 1
    series = prices[-n:]
    rets = []
    for i in range(1, len(series)):
        if series[i - 1] > 0:
            rets.append(series[i] / series[i - 1] - 1.0)
    return rets


def compute_volatility(prices: List[float], lookback: int = _LOOKBACK) -> Optional[float]:
    """연율화 변동성 (일별 수익률 표준편차 × √252).

    Returns None if insufficient data.
    """
    rets = _daily_returns(prices, lookback)
    if len(rets) < 20:
        return None
    mean = sum(rets) / len(rets)
    variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(variance * 252)


def compute_correlation(
    prices_a: List[float],
    prices_b: List[float],
    lookback: int = _LOOKBACK,
) -> Optional[float]:
    """두 자산의 일별 수익률 간 피어슨 상관계수.

    Returns None if insufficient data.
    """
    rets_a = _daily_returns(prices_a, lookback)
    rets_b = _daily_returns(prices_b, lookback)
    n = min(len(rets_a), len(rets_b))
    if n < 20:
        return None
    rets_a = rets_a[-n:]
    rets_b = rets_b[-n:]
    mean_a = sum(rets_a) / n
    mean_b = sum(rets_b) / n
    cov = sum((rets_a[i] - mean_a) * (rets_b[i] - mean_b) for i in range(n)) / (n - 1)
    std_a = math.sqrt(sum((r - mean_a) ** 2 for r in rets_a) / (n - 1))
    std_b = math.sqrt(sum((r - mean_b) ** 2 for r in rets_b) / (n - 1))
    if std_a < 1e-10 or std_b < 1e-10:
        return None
    return max(-1.0, min(1.0, cov / (std_a * std_b)))


def compute_ewp_prices(
    all_prices: Dict[str, List[float]],
) -> List[float]:
    """등비중(Equal-Weighted Portfolio) 일별 가격 인덱스 시계열 반환.

    각 자산의 일별 수익률을 평균하여 누적 인덱스를 구성합니다.
    모든 자산에서 공통으로 사용 가능한 최소 길이를 기준으로 합니다.
    """
    if not all_prices:
        return []
    series_list = list(all_prices.values())
    min_len = min(len(p) for p in series_list)
    if min_len < 2:
        return []
    # 마지막 min_len개 가격으로 맞춤
    trimmed = [p[-min_len:] for p in series_list]
    n = len(series_list)
    ewp = [1.0]
    for i in range(1, min_len):
        avg_ret = sum(
            (trimmed[j][i] / trimmed[j][i - 1] - 1.0)
            for j in range(n)
            if trimmed[j][i - 1] > 0
        ) / n
        ewp.append(ewp[-1] * (1.0 + avg_ret))
    return ewp
