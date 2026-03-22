from typing import Dict, List, Optional

from app.assets.ticker import Ticker

_CACHE: Optional[Dict[str, object]] = None


def _build_candidates(primary: Ticker) -> List[Dict]:
    candidates = [{"ticker": primary.value, "exchange_code": primary.exchange, "priority": 1}]
    priority = 2
    current = primary.alternative
    while current is not None:
        candidates.append({"ticker": current.value, "exchange_code": current.exchange, "priority": priority})
        priority += 1
        current = current.alternative
    return candidates


def _build_maps(data: Dict) -> Dict[str, object]:
    type_to_groups: Dict[str, List[str]] = {}
    group_to_candidates: Dict[str, List[Dict]] = {}
    ticker_to_group: Dict[str, str] = {}
    ticker_to_priority: Dict[str, int] = {}
    ticker_to_exchange: Dict[str, str] = {}

    for asset_type, groups in data.items():
        type_to_groups[asset_type] = [Ticker(g).value for g in groups]
        for primary in groups:
            t_primary = Ticker(primary)
            bucket = group_to_candidates.setdefault(t_primary.value, [])
            for item in _build_candidates(t_primary):
                t = item["ticker"]
                if t in ticker_to_group:
                    continue
                bucket.append(item)
                ticker_to_group[t] = t_primary.value
                ticker_to_priority[t] = int(item["priority"])
                ticker_to_exchange[t] = item["exchange_code"]

    for group, candidates in group_to_candidates.items():
        candidates.sort(key=lambda c: (int(c.get("priority", 1)), c.get("ticker", "")))
        group_to_candidates[group] = candidates

    return {
        "type_to_groups": type_to_groups,
        "group_to_candidates": group_to_candidates,
        "ticker_to_group": ticker_to_group,
        "ticker_to_priority": ticker_to_priority,
        "ticker_to_exchange": ticker_to_exchange,
    }


def _get_cache() -> Dict[str, object]:
    if _CACHE is None:
        raise RuntimeError("assets cache not initialized — call reload_assets() first")
    return _CACHE


def reload_assets(data: Dict) -> None:
    global _CACHE
    _CACHE = _build_maps(data)


def merge_assets(asset_dicts: List[Dict]) -> None:
    """여러 전략의 ASSETS를 병합하여 캐시에 로드한다."""
    merged: Dict = {}
    for data in asset_dicts:
        for asset_type, groups in data.items():
            merged_type = merged.setdefault(asset_type, [])
            for ticker in groups:
                if ticker not in merged_type:
                    merged_type.append(ticker)
    global _CACHE
    _CACHE = _build_maps(merged)


def asset_groups(asset_type: str) -> List[str]:
    cache = _get_cache()
    return list(cache["type_to_groups"].get(asset_type, []))


def all_groups() -> List[str]:
    cache = _get_cache()
    return sorted(cache["group_to_candidates"].keys())


def group_candidates(group: str) -> List[Dict]:
    cache = _get_cache()
    return list(cache["group_to_candidates"].get(group, []))


def group_tiers(group: str) -> List[List[str]]:
    candidates = group_candidates(group)
    tiers: Dict[int, List[str]] = {}
    for item in candidates:
        priority = int(item.get("priority", 1))
        tiers.setdefault(priority, []).append(item["ticker"])
    return [tiers[key] for key in sorted(tiers.keys())]


def group_tickers(group: str) -> List[str]:
    tickers: List[str] = []
    for tier in group_tiers(group):
        tickers.extend(tier)
    return tickers


def group_for_ticker(ticker: str) -> str:
    cache = _get_cache()
    return cache["ticker_to_group"].get(ticker, ticker)


def priority_for_ticker(ticker: str) -> int:
    cache = _get_cache()
    return int(cache["ticker_to_priority"].get(ticker, 1))


def group_tier_index(ticker: str) -> int:
    """ticker의 대체자산 우선순위 인덱스 (0-based). 주자산=0, 대체1=1, …"""
    return priority_for_ticker(ticker) - 1


def group_map() -> Dict[str, List[List[str]]]:
    """전체 그룹→티어 목록 딕셔너리."""
    return {group: group_tiers(group) for group in all_groups()}


def exchange_for_ticker(ticker: str) -> str:
    cache = _get_cache()
    return cache["ticker_to_exchange"].get(ticker, "NASD")
