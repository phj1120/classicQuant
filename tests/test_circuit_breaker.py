"""서킷 브레이커 3-state 전이 회귀 테스트.

오염된 NAV가 하루 튀었다가 되돌아오는 것만으로 defensive↔warning을
반복(whipsaw)하지 않는지, rolling peak/hysteresis/min_hold_days가
의도대로 동작하는지 검증한다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.analytics import circuit_breaker as cb
from app.analytics.risk import rolling_drawdown


@pytest.fixture(autouse=True)
def isolate_state_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "STATE_FILE", tmp_path / "circuit_state.json")


def _history(navs, start_date="2026-01-01"):
    import datetime
    d0 = datetime.date.fromisoformat(start_date)
    return [{"date": (d0 + datetime.timedelta(days=i)).isoformat(), "nav": str(n)} for i, n in enumerate(navs)]


# ── evaluate_circuit_state 3-state 전이 ──────────────────────────────────────

def test_normal_to_warning_transition():
    state = cb.evaluate_circuit_state(current_dd=-0.10, warning_threshold=-0.09, defensive_threshold=-0.18)
    assert state == cb.STATE_WARNING


def test_normal_stays_normal_within_threshold():
    state = cb.evaluate_circuit_state(current_dd=-0.05, warning_threshold=-0.09, defensive_threshold=-0.18)
    assert state == cb.STATE_NORMAL


def test_warning_to_defensive_transition(isolate_state_file):
    cb.save_circuit_state({"state": cb.STATE_WARNING})
    state = cb.evaluate_circuit_state(current_dd=-0.20, warning_threshold=-0.09, defensive_threshold=-0.18)
    assert state == cb.STATE_DEFENSIVE


def test_defensive_recovers_to_warning_after_min_hold():
    """min_hold_days 경과 + 회복 임계 초과 시에만 defensive→warning."""
    state = cb.evaluate_circuit_state(
        current_dd=-0.10, warning_threshold=-0.09, defensive_threshold=-0.18,
        hysteresis=0.05, min_hold_days=5, days_in_state=5,
    )
    assert state == cb.STATE_WARNING


# ── whipsaw 방지: min_hold_days 게이트 ───────────────────────────────────────

def test_defensive_blocks_recovery_before_min_hold(isolate_state_file):
    """defensive 진입 직후 NAV가 반등해도 min_hold_days 전에는 defensive 유지."""
    navs = [1.0] * 10 + [0.6]  # 급락 → defensive 진입
    history = _history(navs)
    dd = rolling_drawdown(navs, window=252)
    state1 = cb.update_circuit_state(
        current_dd=dd, date=history[-1]["date"],
        warning_threshold=-0.09, defensive_threshold=-0.18,
        hysteresis=0.05, min_hold_days=5, history=history,
    )
    assert state1 == cb.STATE_DEFENSIVE

    # 다음날 NAV가 오염으로 튀어 반등한 것처럼 보임 (아직 1거래일 경과)
    navs2 = navs + [0.99]
    history2 = _history(navs2)
    dd2 = rolling_drawdown(navs2, window=252)
    state2 = cb.update_circuit_state(
        current_dd=dd2, date=history2[-1]["date"],
        warning_threshold=-0.09, defensive_threshold=-0.18,
        hysteresis=0.05, min_hold_days=5, history=history2,
    )
    assert state2 == cb.STATE_DEFENSIVE, "min_hold_days 전에는 회복 전이가 차단되어야 한다"


def test_defensive_allows_recovery_after_min_hold_elapsed(isolate_state_file):
    navs = [1.0] * 10 + [0.6]
    history = _history(navs)
    dd = rolling_drawdown(navs, window=252)
    cb.update_circuit_state(
        current_dd=dd, date=history[-1]["date"],
        warning_threshold=-0.09, defensive_threshold=-0.18,
        hysteresis=0.05, min_hold_days=2, history=history,
    )

    # 3거래일 경과 후 반등 지속 → 회복 허용
    navs2 = navs + [0.99, 0.99, 0.99]
    history2 = _history(navs2)
    dd2 = rolling_drawdown(navs2, window=252)
    state2 = cb.update_circuit_state(
        current_dd=dd2, date=history2[-1]["date"],
        warning_threshold=-0.09, defensive_threshold=-0.18,
        hysteresis=0.05, min_hold_days=2, history=history2,
    )
    assert state2 == cb.STATE_WARNING


# ── rolling_drawdown: 오래된 스파이크가 peak로 남지 않아야 함 ─────────────────

def test_rolling_drawdown_ignores_old_spike_outside_window():
    old_spike = [3.0] + [1.0] * 300  # 아주 오래전 고점, 이후 정상 유지
    dd_full_history_would_be = (old_spike[-1] / max(old_spike)) - 1.0
    assert dd_full_history_would_be < -0.6  # 전체 ATH 기준이면 낙폭 과대평가

    dd_rolling = rolling_drawdown(old_spike, window=252)
    assert dd_rolling == 0.0, "window 밖의 오래된 스파이크는 peak에서 제외되어야 한다"


def test_rolling_drawdown_uses_recent_peak():
    navs = [1.0, 1.2, 1.1, 0.9]
    dd = rolling_drawdown(navs, window=252)
    assert abs(dd - (0.9 / 1.2 - 1.0)) < 1e-9
