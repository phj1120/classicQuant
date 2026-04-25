from typing import List
import math


def historical_var(returns: List[float], confidence: float = 0.95) -> float:
    """Historical simulation VaR (음수로 반환, 예: -0.0142 = -1.42%)"""
    if not returns:
        return 0.0
    sorted_returns = sorted(returns)
    index = int(len(sorted_returns) * (1 - confidence))
    index = max(0, min(index, len(sorted_returns) - 1))
    return sorted_returns[index]


def cvar(returns: List[float], confidence: float = 0.95) -> float:
    """CVaR / Expected Shortfall (음수로 반환)"""
    if not returns:
        return 0.0
    sorted_returns = sorted(returns)
    cutoff_index = int(len(sorted_returns) * (1 - confidence))
    if cutoff_index == 0:
        return sorted_returns[0]
    tail = sorted_returns[:cutoff_index]
    return sum(tail) / len(tail)


def max_drawdown(returns: List[float]) -> float:
    """누적 NAV 기반 최대 낙폭 (음수, 예: -0.1548)"""
    if not returns:
        return 0.0
    nav = 1.0
    peak = 1.0
    mdd = 0.0
    for r in returns:
        nav *= (1 + r)
        if nav > peak:
            peak = nav
        dd = (nav - peak) / peak
        if dd < mdd:
            mdd = dd
    return mdd


def annualized_sharpe(returns: List[float], trading_days: int = 252) -> float:
    """연환산 Sharpe ratio"""
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance)
    if std == 0.0:
        return 0.0
    return (mean / std) * math.sqrt(trading_days)
