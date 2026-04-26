"""MDD 기반 3-state 서킷 브레이커.

상태 전이:
  normal    → warning:   낙폭 >= warning_threshold
  warning   → defensive: 낙폭 >= defensive_threshold
  defensive → warning:   낙폭 <= recovery_threshold (= defensive_threshold + hysteresis)
  warning   → normal:    낙폭 <= normal_recovery (= warning_threshold + hysteresis)

상태는 data/circuit_state.json에 저장된다.
"""
import json
from pathlib import Path
from typing import Optional

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
) -> str:
    """현재 낙폭과 이전 상태를 기반으로 새 상태를 반환한다.

    히스테리시스로 상태가 빠르게 전환되는 것을 방지한다.

    Args:
        current_dd: 현재 고점 대비 낙폭 (음수, e.g. -0.15 = -15%)
        warning_threshold: warning 진입 임계값 (e.g. -0.10)
        defensive_threshold: defensive 진입 임계값 (e.g. -0.20)
        hysteresis: 회복 시 추가 완충 (e.g. 0.03 = 3%)

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
        if current_dd > recovery_threshold:
            new_state = STATE_WARNING
        else:
            new_state = STATE_DEFENSIVE

    return new_state


def update_circuit_state(
    current_dd: float,
    date: str,
    warning_threshold: float = DEFAULT_WARNING_THRESHOLD,
    defensive_threshold: float = DEFAULT_DEFENSIVE_THRESHOLD,
    hysteresis: float = DEFAULT_HYSTERESIS,
) -> str:
    """상태를 평가하고 파일에 저장한 후 새 상태를 반환한다."""
    new_state = evaluate_circuit_state(
        current_dd, warning_threshold, defensive_threshold, hysteresis
    )
    save_circuit_state({
        "state": new_state,
        "current_dd": round(current_dd, 6),
        "date": date,
        "warning_threshold": warning_threshold,
        "defensive_threshold": defensive_threshold,
        "hysteresis": hysteresis,
    })
    return new_state
