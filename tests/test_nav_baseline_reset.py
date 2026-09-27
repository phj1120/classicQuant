"""NAV 비교 기준 재설정(--reset-nav-baseline)과 낡은 기준 거부 회귀 테스트.

2026-07-29 이후 현금 조회 오류로 NAV 기록이 중단되고 서킷 브레이커가 오염 구간
고점 기준 낙폭에 고착됐던 상황을 재현해, 재설정 후 정상 운용으로 복귀하는지 검증한다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import run_rebalance
from app.analytics import audit_log, csv_logger
from app.analytics import circuit_breaker as cb

SELECTION_CFG = {
    "portfolio_mdd_limit": -0.18,
    "rolling_peak_window": 252,
    "circuit_hysteresis": 0.05,
    "circuit_min_hold_days": 5,
}
NAV_CFG = {"sanity_max_daily_return": 0.10, "stale_baseline_max_days": 5}


@pytest.fixture(autouse=True)
def isolate_data_files(tmp_path, monkeypatch):
    monkeypatch.setattr(csv_logger, "PORTFOLIO_NAV_ACTUAL_CSV", tmp_path / "portfolio_nav_actual.csv")
    monkeypatch.setattr(csv_logger, "PORTFOLIO_NAV_LEGACY_CSV", tmp_path / "portfolio_nav_legacy_absent.csv")
    monkeypatch.setattr(csv_logger, "PORTFOLIO_STATE_CSV", tmp_path / "portfolio_state.csv")
    monkeypatch.setattr(csv_logger, "CASH_FLOWS_CSV", tmp_path / "cash_flows.csv")
    monkeypatch.setattr(audit_log, "AUDIT_LOG_CSV", tmp_path / "audit_log.csv")
    monkeypatch.setattr(cb, "STATE_FILE", tmp_path / "circuit_state.json")
    monkeypatch.setattr(run_rebalance, "_NAV_BASELINE_PATH", tmp_path / "nav_baseline.json")
    monkeypatch.setattr(run_rebalance, "get_usdkrw_rate", lambda date: 1300.0)


def _seed_stuck_state():
    """오염 고점(3.0) 이후 2.27에서 기록이 멈추고 defensive에 고착된 상태."""
    csv_logger.save_portfolio_nav_actual("2026-07-24", 3.0, 0.0, total_equity=1233.14)
    csv_logger.save_portfolio_nav_actual("2026-07-29", 2.272477, 0.0, total_equity=920.07)
    csv_logger.save_portfolio_state("2026-07-29", 920.07, 0.0)
    cb.save_circuit_state({"state": cb.STATE_DEFENSIVE, "entered_date": "2026-07-28", "current_dd": -0.2408})


def test_stale_baseline_is_rejected_even_with_small_change():
    _seed_stuck_state()
    recorded = run_rebalance._update_portfolio_nav_actual("2026-09-28", 925.0, 925.0, nav_cfg=NAV_CFG)
    assert recorded is False
    assert "NAV_REJECTED" in audit_log.AUDIT_LOG_CSV.read_text(encoding="utf-8")


def test_reset_records_new_baseline_and_clears_circuit():
    _seed_stuck_state()
    run_rebalance._reset_nav_baseline("2026-09-28", 1240.0, 1240.0)

    rows = csv_logger.load_portfolio_nav_actual()
    assert rows[-1]["date"] == "2026-09-28"
    assert float(rows[-1]["nav"]) == pytest.approx(2.272477)  # NAV는 이어간다
    assert float(rows[-1]["daily_return"]) == 0.0
    assert csv_logger.load_portfolio_state()[-1]["date"] == "2026-09-28"
    assert json.loads(run_rebalance._NAV_BASELINE_PATH.read_text(encoding="utf-8"))["reset_date"] == "2026-09-28"
    assert cb.load_circuit_state()["state"] == cb.STATE_NORMAL
    assert "NAV_BASELINE_RESET" in audit_log.AUDIT_LOG_CSV.read_text(encoding="utf-8")


def test_next_day_after_reset_records_nav():
    _seed_stuck_state()
    run_rebalance._reset_nav_baseline("2026-09-28", 1240.0, 1240.0)
    recorded = run_rebalance._update_portfolio_nav_actual("2026-09-29", 1246.2, 300.0, nav_cfg=NAV_CFG)
    assert recorded is True
    assert float(csv_logger.load_portfolio_nav_actual()[-1]["daily_return"]) == pytest.approx(0.005)


def test_circuit_ignores_peak_before_reset():
    _seed_stuck_state()
    # 재설정 전에는 오염 고점(3.0) 기준 -24% 낙폭으로 defensive
    triggered, dd, _ = run_rebalance._check_portfolio_mdd(SELECTION_CFG, "2026-09-25")
    assert triggered is True
    assert dd == pytest.approx(2.272477 / 3.0 - 1.0)

    run_rebalance._reset_nav_baseline("2026-09-28", 1240.0, 1240.0)
    triggered, dd, state = run_rebalance._check_portfolio_mdd(SELECTION_CFG, "2026-09-28")
    assert triggered is False
    assert dd == 0.0
    assert state == cb.STATE_NORMAL
