import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ASSETS_PATH = Path(__file__).resolve().parent / "strategies" / "daa" / "assets.json"

_CACHE: Optional[Dict[str, object]] = None


def _load_raw(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_maps(data: Dict) -> Dict[str, object]:
    type_to_groups: Dict[str, List[str]] = {}
    group_to_candidates: Dict[str, List[Dict]] = {}
    ticker_to_group: Dict[str, str] = {}
    ticker_to_priority: Dict[str, int] = {}
    ticker_to_exchange: Dict[str, str] = {}

    for asset_type, groups in data.items():
        type_to_groups[asset_type] = list(groups.keys())
        for group, candidates in groups.items():
            bucket = group_to_candidates.setdefault(group, [])
            for item in candidates:
                ticker = item["ticker"]
                if ticker in ticker_to_group:
                    continue
                bucket.append(item)
                ticker_to_group[ticker] = group
                ticker_to_priority[ticker] = int(item.get("priority", 1))
                ticker_to_exchange[ticker] = item.get("exchange_code", "NASD")

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


def _get_cache(path: Path = ASSETS_PATH) -> Dict[str, object]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _build_maps(_load_raw(path))
    return _CACHE


def reload_assets(path: Path = ASSETS_PATH) -> None:
    global _CACHE
    _CACHE = _build_maps(_load_raw(path))


def merge_assets_files(paths: List[Path]) -> None:
    """여러 전략의 assets.json을 병합하여 캐시에 로드한다."""
    merged: Dict = {}
    for path in paths:
        raw = _load_raw(path)
        for asset_type, groups in raw.items():
            merged_type = merged.setdefault(asset_type, {})
            for group, candidates in groups.items():
                existing = merged_type.setdefault(group, [])
                existing_tickers = {c["ticker"] for c in existing}
                for c in candidates:
                    if c["ticker"] not in existing_tickers:
                        existing.append(c)
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


def exchange_for_ticker(ticker: str) -> str:
    cache = _get_cache()
    return cache["ticker_to_exchange"].get(ticker, "NASD")
