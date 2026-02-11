from typing import Dict, List, Optional

from app.constants import LOOKBACK_DAYS
from app.data_utils import parse_history
from app.exchange import set_exchange_for_ticker
from app.groups import group_tickers
from app.kis_api import KoreaInvestmentAPI


def compute_return(prices: List[float], lookback: int) -> Optional[float]:
    if len(prices) <= lookback:
        return None
    current = prices[-1]
    past = prices[-1 - lookback]
    if past <= 0:
        return None
    return (current / past) - 1.0


def compute_momentum(prices: List[float]) -> tuple[Optional[float], Dict[str, Optional[float]]]:
    r1 = compute_return(prices, LOOKBACK_DAYS["1m"])
    r3 = compute_return(prices, LOOKBACK_DAYS["3m"])
    r6 = compute_return(prices, LOOKBACK_DAYS["6m"])
    r12 = compute_return(prices, LOOKBACK_DAYS["12m"])

    returns = {"r1m": r1, "r3m": r3, "r6m": r6, "r12m": r12}

    if None in (r1, r3, r6, r12):
        return None, returns

    return (r1 * 12) + (r3 * 4) + (r6 * 2) + (r12 * 1), returns


def get_momentum_scores(
    api: KoreaInvestmentAPI, groups: List[str],
) -> tuple[Dict[str, Optional[float]], Dict[str, Dict[str, Optional[float]]], Dict[str, list]]:
    scores: Dict[str, Optional[float]] = {}
    all_returns: Dict[str, Dict[str, Optional[float]]] = {}
    all_histories: Dict[str, list] = {}
    for group in groups:
        score = None
        returns: Dict[str, Optional[float]] = {}
        for ticker in group_tickers(group):
            set_exchange_for_ticker(api, ticker)
            history = api.get_historical_data(ticker, period="D", min_records=260)
            if not history:
                continue
            prices = parse_history(history)
            score, returns = compute_momentum(prices)
            all_histories[ticker] = history
            if score is not None:
                break
        scores[group] = score
        all_returns[group] = returns
        if score is None:
            print(f"⚠️  모멘텀 계산 실패: {group} (데이터 부족)")
    return scores, all_returns, all_histories
