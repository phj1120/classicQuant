"""run_rebalance._update_portfolio_nav_actual의 sanity gate / 입출금 보정 회귀 테스트.

실제 data/ 디렉터리와 외부 API(환율 조회)를 건드리지 않도록 관련 모듈 상수와
함수를 tmp_path/monkeypatch로 격리한다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import run_rebalance
from app.analytics import csv_logger, audit_log


@pytest.fixture(autouse=True)
def isolate_data_files(tmp_path, monkeypatch):
    monkeypatch.setattr(csv_logger, "PORTFOLIO_NAV_ACTUAL_CSV", tmp_path / "portfolio_nav_actual.csv")
    monkeypatch.setattr(csv_logger, "PORTFOLIO_NAV_LEGACY_CSV", tmp_path / "portfolio_nav_legacy_absent.csv")
    monkeypatch.setattr(csv_logger, "PORTFOLIO_STATE_CSV", tmp_path / "portfolio_state.csv")
    monkeypatch.setattr(csv_logger, "CASH_FLOWS_CSV", tmp_path / "cash_flows.csv")
    monkeypatch.setattr(audit_log, "AUDIT_LOG_CSV", tmp_path / "audit_log.csv")
    # 환율 조회는 외부 API 호출이라 고정값으로 대체
    monkeypatch.setattr(run_rebalance, "get_usdkrw_rate", lambda date: 1300.0)


def _seed_history(prev_equity: float, prev_nav: float = 1.0, date: str = "2026-07-26"):
    csv_logger.save_portfolio_state(date, prev_equity, prev_equity * 0.1)
    csv_logger.save_portfolio_nav_actual(date, prev_nav, 0.0, total_equity=prev_equity)


def test_normal_return_is_recorded():
    _seed_history(prev_equity=1000.0)
    recorded = run_rebalance._update_portfolio_nav_actual("2026-07-27", 1020.0, 400.0, nav_cfg={"sanity_max_daily_return": 0.10})
    assert recorded is True
    rows = csv_logger.load_portfolio_nav_actual()
    assert len(rows) == 2
    assert abs(float(rows[-1]["daily_return"]) - 0.02) < 1e-6


def test_extreme_return_is_rejected():
    """체결 전 잔고 재조회로 인한 +47% 같은 튐은 기록을 거부해야 한다."""
    _seed_history(prev_equity=1239.48)
    recorded = run_rebalance._update_portfolio_nav_actual("2026-07-27", 841.01, 392.18, nav_cfg={"sanity_max_daily_return": 0.10})
    assert recorded is False
    rows = csv_logger.load_portfolio_nav_actual()
    assert len(rows) == 1  # 오염된 값이 추가되지 않음
    # 거부 사유가 audit log에 남아야 한다
    assert audit_log.AUDIT_LOG_CSV.exists()
    assert "NAV_REJECTED" in audit_log.AUDIT_LOG_CSV.read_text(encoding="utf-8")


def test_cash_flow_adjustment_prevents_false_spike():
    """입금 500달러가 있었던 날은 그 금액을 빼고 수익률을 계산해야 한다."""
    _seed_history(prev_equity=1000.0)
    csv_logger.CASH_FLOWS_CSV.parent.mkdir(parents=True, exist_ok=True)
    csv_logger.CASH_FLOWS_CSV.write_text("date,amount_usd,memo\n2026-07-27,500,입금\n", encoding="utf-8")

    recorded = run_rebalance._update_portfolio_nav_actual("2026-07-27", 1510.0, 900.0, nav_cfg={"sanity_max_daily_return": 0.10})
    assert recorded is True
    rows = csv_logger.load_portfolio_nav_actual()
    # (1510-500)/1000 - 1 = 0.01 이지 (1510/1000 - 1) = 0.51이 아니어야 한다
    assert abs(float(rows[-1]["daily_return"]) - 0.01) < 1e-6


def test_first_snapshot_without_history_uses_zero_return():
    """이전 상태가 전혀 없으면(최초 실행) daily_return=0으로 시작해야 한다."""
    recorded = run_rebalance._update_portfolio_nav_actual("2026-07-27", 1000.0, 500.0, nav_cfg={"sanity_max_daily_return": 0.10})
    assert recorded is True
    rows = csv_logger.load_portfolio_nav_actual()
    assert len(rows) == 1
    assert float(rows[0]["daily_return"]) == 0.0
