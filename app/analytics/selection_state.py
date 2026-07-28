"""월간 전략 선택 상태 저장/로드.

selection.rebalance_frequency="monthly"일 때, 매월 첫 실행에서만
corr_constrained 재계산을 수행하고 나머지 거래일은 저장된 조합을 재사용한다.
매일 재선택하면 랭킹 경계에서 근소한 순위 변동만으로도 전량 리밸런싱이
발생해(114거래일 중 33회 교체 관측) 회전 비용이 알파를 잠식하기 때문이다.

상태는 data/selection_state.json에 저장된다.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path("data")
STATE_FILE = DATA_DIR / "selection_state.json"


def load_selection_state() -> Dict:
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_selection_state(selected_month: str, selected_date: str, selected: List[Dict]) -> None:
    """selected: select_active_strategies()가 반환하는 [{"name":..., "weight":...}, ...] 그대로 저장."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "selected_month": selected_month,
                "selected_date": selected_date,
                "selected": selected,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
