import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from app.constants import (
    DEFAULT_CASH_BUFFER_PCT,
    DEFAULT_CHECK_HOLIDAY,
    DEFAULT_EXECUTION_OFFSET_MINUTES,
    DEFAULT_EXECUTION_WINDOW_MINUTES,
    DEFAULT_MIN_TRADE_VALUE_USD,
    DEFAULT_REBALANCE_THRESHOLD_PCT,
    KIS_BASE_URL,
    KIS_EXCHANGE_CODE,
)

_ENV_KEY_MAP = {
    "app_key": "KIS_APP_KEY",
    "app_secret": "KIS_APP_SECRET",
    "account_number": "KIS_ACCOUNT_NUMBER",
    "account_code": "KIS_ACCOUNT_CODE",
}


def load_config(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_key(path: Optional[Path] = None) -> Dict:
    """key.json 파일 또는 환경변수에서 API 키를 로드한다."""
    if path and path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    key = {}
    for field, env_var in _ENV_KEY_MAP.items():
        val = os.environ.get(env_var)
        if val:
            key[field] = val

    missing = [env for field, env in _ENV_KEY_MAP.items() if field not in key]
    if missing:
        raise RuntimeError(
            f"API 키를 찾을 수 없습니다. key.json 파일을 지정하거나 "
            f"환경변수를 설정하세요: {', '.join(missing)}"
        )
    return key


def build_kis_config(key: Dict) -> Dict:
    return {
        **key,
        "base_url": KIS_BASE_URL,
        "exchange_code": KIS_EXCHANGE_CODE,
    }


def build_execution_config(raw: Dict) -> Dict:
    return {
        "market_open_plus": True,
        "offset_minutes": DEFAULT_EXECUTION_OFFSET_MINUTES,
        "window_minutes": DEFAULT_EXECUTION_WINDOW_MINUTES,
        "check_holiday": DEFAULT_CHECK_HOLIDAY,
        **raw.get("execution", {}),
    }


def build_strategy_config(raw: Dict) -> Dict:
    return {
        "cash_buffer_pct": DEFAULT_CASH_BUFFER_PCT,
        "min_trade_value_usd": DEFAULT_MIN_TRADE_VALUE_USD,
        "rebalance_threshold_pct": DEFAULT_REBALANCE_THRESHOLD_PCT,
        **raw.get("strategy", {}),
    }


def load_strategy_entries(raw: Dict) -> List[Dict]:
    """config.json의 strategies 배열에서 전략 목록을 로드한다.

    weight 필드가 있으면 정규화하여 사용, 없으면 균등 배분 (나중에 선택 로직이 재계산).
    """
    data = raw.get("strategies", [])
    if not data:
        from app.strategies import _REGISTRY
        data = [{"name": name} for name in _REGISTRY]
    has_weights = any("weight" in e for e in data)
    if has_weights:
        total = sum(e.get("weight", 1.0) for e in data)
        return [
            {
                "name": e.get("name", "daa"),
                "weight": e.get("weight", 1.0) / total,
            }
            for e in data
        ]
    # weight 없음 → 균등 배분 (선택 로직에서 active 전략만 재계산)
    n = len(data)
    return [
        {
            "name": e.get("name", "daa"),
            "weight": 1.0 / n,
        }
        for e in data
    ]


def load_selection_config(raw: Dict) -> Dict:
    """config.json의 selection 섹션을 로드한다."""
    defaults = {
        "criteria": "strategy_momentum",
        "top_n": None,
        "mdd_filter_threshold": None,
        "min_active_strategies": 1,
        "fallback_strategy": "permanent",
        "corr_threshold": 0.7,
        "corr_window": 63,
    }
    return {**defaults, **raw.get("selection", {})}
