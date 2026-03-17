"""SMA(Simple Moving Average) 계산 유틸리티.

GTAA, Ivy, LAA 전략의 추세 시그널에 사용됩니다.
"""
from typing import List, Optional

SMA_10M = 21 * 10   # 10개월 ≈ 210 거래일 (GTAA, Ivy)
SMA_200D = 200       # 200일 SMA (LAA 추세 필터)


def compute_sma(prices: List[float], period: int) -> Optional[float]:
    """단순이동평균. 데이터가 period개 미만이면 None."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def is_above_sma(prices: List[float], period: int) -> Optional[bool]:
    """현재 가격(prices[-1])이 period일 SMA 위에 있으면 True.

    SMA는 최근 period개 가격(현재 포함)으로 계산합니다.
    데이터 부족 시 None을 반환합니다.
    """
    sma = compute_sma(prices, period)
    if sma is None or not prices:
        return None
    return prices[-1] > sma
