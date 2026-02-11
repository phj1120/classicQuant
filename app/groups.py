from typing import Dict, List

from app.assets import (
    all_groups,
    group_for_ticker as _group_for_ticker,
    group_tiers as _group_tiers,
    group_tickers as _group_tickers,
    priority_for_ticker as _priority_for_ticker,
)


def group_for_ticker(ticker: str) -> str:
    return _group_for_ticker(ticker)


def group_tiers(group: str) -> List[List[str]]:
    return _group_tiers(group)


def group_tickers(group: str) -> List[str]:
    return _group_tickers(group)


def group_tier_index(ticker: str) -> int:
    return _priority_for_ticker(ticker) - 1


def group_map() -> Dict[str, List[List[str]]]:
    return {group: _group_tiers(group) for group in all_groups()}
