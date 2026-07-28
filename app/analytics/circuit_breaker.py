"""MDD 기반 3-state 서킷 브레이커.

상태 전이:
  normal    → warning:   낙폭 >= warning_threshold
  warning   → defensive: 낙폭 >= defensive_threshold
  defensive → warning:   낙폭 <= recovery_threshold (= defensive_threshold + hysteresis)
                         AND min_hold_days 이상 defensive 상태 유지된 경우
  warning   → normal:    낙폭 <= normal_recovery (= warning_threshold + hysteresis)

상태는 data/circuit_state.json에 저장된다. min_hold_days는 오염된 NAV가
하루 튀었다가 되돌아오는 것만으로 상태가 반복 전환(whipsaw)되는 것을 막는다.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path("data")
STATE_FILE = DATA_DIR / "circuit_state.json"

STATE_NORMAL = "normal"
STATE_WARNING = "warning"
STATE_DEFENSIVE = "defensive"

DEFAULT_WARNING_THRESHOLD = -0.10    # -10%
DEFAULT_DEFENSIVE_THRESHOLD = -0.20  # -20%
DEFAULT_HYSTERESIS = 0.03            # 3% 회복 필요


def load_circuit_state() -> dict:
    """현재 서킷 브레이커 상태를 파일에서 로드한다."""
    if not STATE_FILE.exists():
        return {"state": STATE_NORMAL}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("state") not in (STATE_NORMAL, STATE_WARNING, STATE_DEFENSIVE):
            data["state"] = STATE_NORMAL
        return data
    except Exception:
        return {"state": STATE_NORMAL}


def save_circuit_state(state_dict: dict) -> None:
    """서킷 브레이커 상태를 파일에 저장한다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state_dict, f, ensure_ascii=False, indent=2)


def evaluate_circuit_state(
    current_dd: float,
    warning_threshold: float = DEFAULT_WARNING_THRESHOLD,
    defensive_threshold: float = DEFAULT_DEFENSIVE_THRESHOLD,
    hysteresis: float = DEFAULT_HYSTERESIS,
    min_hold_days: int = 0,
    days_in_state: int = 0,
) -> str:
    """현재 낙폭과 이전 상태를 기반으로 새 상태를 반환한다.

    히스테리시스로 상태가 빠르게 전환되는 것을 방지한다.

    Args:
        current_dd: 현재 고점 대비 낙폭 (음수, e.g. -0.15 = -15%)
        warning_threshold: warning 진입 임계값 (e.g. -0.10)
        defensive_threshold: defensive 진입 임계값 (e.g. -0.20)
        hysteresis: 회복 시 추가 완충 (e.g. 0.03 = 3%)
        min_hold_days: defensive 진입 후 회복 전이가 가능해지기까지 필요한
            최소 거래일 수. 하루 반등만으로 재진입/이탈을 반복하는 것을 막는다.
        days_in_state: 현재 상태를 유지한 거래일 수 (호출자가 계산해 전달)

    Returns:
        STATE_NORMAL, STATE_WARNING, or STATE_DEFENSIVE
    """
    prev_state_dict = load_circuit_state()
    prev_state = prev_state_dict.get("state", STATE_NORMAL)

    if prev_state == STATE_NORMAL:
        if current_dd <= defensive_threshold:
            new_state = STATE_DEFENSIVE
        elif current_dd <= warning_threshold:
            new_state = STATE_WARNING
        else:
            new_state = STATE_NORMAL

    elif prev_state == STATE_WARNING:
        if current_dd <= defensive_threshold:
            new_state = STATE_DEFENSIVE
        elif current_dd > warning_threshold + hysteresis:
            new_state = STATE_NORMAL
        else:
            new_state = STATE_WARNING

    else:  # STATE_DEFENSIVE
        recovery_threshold = defensive_threshold + hysteresis
        if current_dd > recovery_threshold and days_in_state >= min_hold_days:
            new_state = STATE_WARNING
        else:
            new_state = STATE_DEFENSIVE

    return new_state


def _trading_days_since(history: Optional[List[Dict]], since_date: str) -> int:
    """history(날짜 오름차순 NAV 행 목록)에서 since_date 이후(제외) 거래일 수를 센다."""
    if not history or not since_date:
        return 0
    return sum(1 for row in history if row.get("date", "") > since_date)


def update_circuit_state(
    current_dd: float,
    date: str,
    warning_threshold: float = DEFAULT_WARNING_THRESHOLD,
    defensive_threshold: float = DEFAULT_DEFENSIVE_THRESHOLD,
    hysteresis: float = DEFAULT_HYSTERESIS,
    min_hold_days: int = 0,
    history: Optional[List[Dict]] = None,
) -> str:
    """상태를 평가하고 파일에 저장한 후 새 상태를 반환한다.

    history를 전달하면(포트폴리오 NAV 행 목록), entered_date 이후 경과한
    거래일 수를 세어 min_hold_days 게이트에 사용한다. 생략하면 게이트 없이
    (기존 동작 그대로) 즉시 회복 전이를 허용한다.
    """
    prev_state_dict = load_circuit_state()
    prev_state = prev_state_dict.get("state", STATE_NORMAL)
    entered_date = prev_state_dict.get("entered_date", date)

    days_in_state = (
        _trading_days_since(history, entered_date) if history is not None else min_hold_days
    )

    new_state = evaluate_circuit_state(
        current_dd, warning_threshold, defensive_threshold, hysteresis,
        min_hold_days=min_hold_days, days_in_state=days_in_state,
    )

    if new_state != prev_state:
        entered_date = date

    save_circuit_state({
        "state": new_state,
        "current_dd": round(current_dd, 6),
        "date": date,
        "nav_date": date,
        "entered_date": entered_date,
        "warning_threshold": warning_threshold,
        "defensive_threshold": defensive_threshold,
        "hysteresis": hysteresis,
        "min_hold_days": min_hold_days,
    })
    return new_state
